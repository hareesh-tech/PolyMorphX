#!/usr/bin/env python3
"""
Transformation Engine v3.0 - Multi-Pass Architecture
=====================================================

Pass 1: Instruction substitution (size-preserving, in-place) only.
Junk insertion is now handled by a separate module.

Diversification strategies:
  - DivideAndTransformAllocator  : Category-based % allocation with smart shuffling
  - SeededMultiPassSelector      : Seeded randomness + lineage-aware candidate selection
  - LineageTracker               : SQLite-backed history to avoid repeated choices

Usage:
  python transformation.py --plan plan.json --exe target.exe -o output/
  python transformation.py --plan plan.json --exe target.exe -o output/ -d -l
"""

import json
import random
import hashlib
import logging
import argparse
import time
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import sqlite3

# ---------------------------------------------------------------------------
# Module-level globals
# ---------------------------------------------------------------------------
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger("TransformEngine")


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class AppliedTransform:
    """Record of a single instruction-level transformation."""
    address: int
    original_asm: str
    new_asm: str
    original_bytes: str
    new_bytes: str
    applied: bool
    reason: str
    transform_type: str = ""


@dataclass
class TransformedBlock:
    """Result of transforming a basic block with junk insertion."""
    start_addr: int
    original_bytes: bytes
    instruction_substitutions: Dict[int, str]   # offset -> new_bytes hex
    pre_junk: bytes
    post_junk: bytes
    final_bytes: bytes
    new_address: int = 0                         # Absolute offset in final binary


@dataclass
class TransformationCategory:
    """Defines a transformation pattern category with alternatives."""
    name: str
    patterns: List[str]
    alternatives: List[Dict]
    total_allocation: float


# ============================================================================
# LINEAGE TRACKING DATABASE
# ============================================================================

class LineageTracker:
    """
    Tracks transformation history across builds using SQLite.
    Ensures candidate diversity by excluding recently-used choices.
    """

    def __init__(self, db_path: Path = Path("transformation_lineage.db")):
        self.db_path = db_path
        try:
            self._init_db()
        except Exception as exc:
            logger.error(f"Failed to initialise lineage database: {exc}")
            raise

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create schema if it does not already exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transformation_lineage (
                id                         INTEGER PRIMARY KEY AUTOINCREMENT,
                semantic_id                TEXT    NOT NULL,
                build_timestamp            TEXT    NOT NULL,
                seed_used                  INTEGER NOT NULL,
                choice_made                INTEGER NOT NULL,
                bytes_produced             TEXT    NOT NULL,
                hamming_distance_to_prev   INTEGER,
                build_id                   TEXT    NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_semantic_id
            ON transformation_lineage(semantic_id)
        """)

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def record_choice(self, semantic_id: str, seed: int, choice_idx: int,
                      bytes_produced: str, build_id: str) -> None:
        """Persist a transformation choice for future lineage queries."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            prev_bytes = self._get_recent_bytes(semantic_id, limit=1)
            hamming_dist = (
                self._hamming_distance(bytes_produced, prev_bytes[0])
                if prev_bytes else None
            )

            cursor.execute("""
                INSERT INTO transformation_lineage
                    (semantic_id, build_timestamp, seed_used, choice_made,
                     bytes_produced, hamming_distance_to_prev, build_id)
                VALUES (?, datetime('now'), ?, ?, ?, ?, ?)
            """, (semantic_id, seed, choice_idx, bytes_produced, hamming_dist, build_id))

            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning(f"Failed to record lineage for {semantic_id}: {exc}")

    def get_excluded_choices(self, semantic_id: str,
                             similarity_threshold: float = 0.8) -> Set[int]:
        """
        Return candidate indices to skip for this semantic ID.
        Excludes the two most recent choices to maximise build diversity.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT choice_made, bytes_produced
                FROM transformation_lineage
                WHERE semantic_id = ?
                ORDER BY build_timestamp DESC
                LIMIT 5
            """, (semantic_id,))

            recent = cursor.fetchall()
            conn.close()

            excluded: Set[int] = set()
            if len(recent) >= 1:
                excluded.add(recent[0][0])
            if len(recent) >= 2:
                excluded.add(recent[1][0])

            return excluded
        except Exception:
            return set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_recent_bytes(self, semantic_id: str, limit: int = 5) -> List[str]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT bytes_produced FROM transformation_lineage
                WHERE semantic_id = ?
                ORDER BY build_timestamp DESC
                LIMIT ?
            """, (semantic_id, limit))
            results = [row[0] for row in cursor.fetchall()]
            conn.close()
            return results
        except Exception:
            return []

    @staticmethod
    def _hamming_distance(bytes1: str, bytes2: str) -> int:
        try:
            if len(bytes1) != len(bytes2):
                return max(len(bytes1), len(bytes2))
            b1 = bytes.fromhex(bytes1)
            b2 = bytes.fromhex(bytes2)
            return sum(bin(x ^ y).count("1") for x, y in zip(b1, b2))
        except Exception:
            return 0


# ============================================================================
# DIVIDE AND TRANSFORM ALLOCATOR
# ============================================================================

class DivideAndTransformAllocator:
    """
    Allocates transformation slots by category percentage.
    Ensures diverse transformation type coverage across the binary.
    """

    DEFAULT_ALLOCATIONS: Dict[str, float] = {
        "ZEROING":    0.25,   # XOR <=> SUB zeroing patterns
        "MOV":        0.35,   # MOV register variants
        "COMPARISON": 0.30,   # TEST <=> AND comparisons
        "ARITHMETIC": 0.10,   # CMP / ADD / SUB arithmetic
    }

    def __init__(self, allocations: Optional[Dict[str, float]] = None):
        if allocations:
            self.allocations = dict(allocations)
        else:
            self._smart_shuffle()
        self._validate_allocations()

    # ------------------------------------------------------------------
    # Allocation generation
    # ------------------------------------------------------------------

    def _smart_shuffle(self) -> None:
        """
        Randomly redistribute allocations while guaranteeing a 5 % floor
        for every category so no type is completely suppressed.
        """
        keys = list(self.DEFAULT_ALLOCATIONS.keys())
        allocations = {k: 0.05 for k in keys}
        remaining = 1.0 - sum(allocations.values())

        weights = {k: random.random() for k in keys}
        total_w = sum(weights.values())

        for k in keys:
            allocations[k] += (weights[k] / total_w) * remaining
            allocations[k] = round(allocations[k], 3)

        # Normalise to exactly 1.0
        diff = 1.0 - sum(allocations.values())
        max_key = max(allocations, key=allocations.get)
        allocations[max_key] += diff

        self.allocations = allocations
        logger.info(f"Smart-shuffled allocations: {self.allocations}")

    def _validate_allocations(self) -> None:
        total = sum(self.allocations.values())
        if abs(total - 1.0) > 0.001:
            logger.warning(f"Allocations sum to {total:.4f} — normalising to 1.0")
            factor = 1.0 / total
            for k in self.allocations:
                self.allocations[k] *= factor

    def vary_allocations(self, seed: int) -> Dict[str, float]:
        """
        Perturb each allocation by ±10 % relative to the current values,
        maintaining sum=1.0.  Returns a *new* allocation dict.
        """
        random.seed(seed)
        varied = {
            k: max(0.05, min(0.5, v + random.uniform(-0.1, 0.1)))
            for k, v in self.allocations.items()
        }
        total = sum(varied.values())
        for k in varied:
            varied[k] /= total
        logger.info(f"Varied allocations (seed={seed}): {varied}")
        return varied

    # ------------------------------------------------------------------
    # Plan analysis & selection
    # ------------------------------------------------------------------

    def categorize_plan_entries(self, plan: List[Dict]) -> Dict[str, List[int]]:
        """
        Map each AVAILABLE plan entry to one of the known categories.
        Returns {category: [plan_indices]}.
        """
        categories: Dict[str, List[int]] = defaultdict(list)

        for i, entry in enumerate(plan):
            if entry.get("status") != "AVAILABLE":
                continue
            types = [c.get("type", "") for c in entry.get("candidates", [])]
            if any("ZERO" in t for t in types):
                categories["ZEROING"].append(i)
            elif any("MOV" in t for t in types):
                categories["MOV"].append(i)
            elif any("TEST" in t or "AND" in t for t in types):
                categories["COMPARISON"].append(i)
            elif any("CMP" in t or "ADD" in t or "SUB" in t for t in types):
                categories["ARITHMETIC"].append(i)
            else:
                categories["OTHER"].append(i)

        return dict(categories)

    def allocate_transformations(self, plan: List[Dict],
                                  total_count: int) -> List[int]:
        """
        Select up to *total_count* plan indices honoring category percentages.
        Any shortfall is filled from the remaining pool.
        """
        if total_count <= 0:
            return []

        categories = self.categorize_plan_entries(plan)
        selected: List[int] = []

        for category, allocation in self.allocations.items():
            available = categories.get(category, [])
            target = int(total_count * allocation)
            if len(available) <= target:
                selected.extend(available)
                logger.info(f"  {category}: {len(available)}/{target} (all available)")
            else:
                selected.extend(random.sample(available, target))
                logger.info(f"  {category}: {target} selected")

        # Fill shortfall from unallocated entries
        remaining = total_count - len(selected)
        if remaining > 0:
            pool = [
                i for i, p in enumerate(plan)
                if p.get("status") == "AVAILABLE" and i not in selected
            ]
            if len(pool) >= remaining:
                selected.extend(random.sample(pool, remaining))
                logger.info(f"  Filled {remaining} from remaining pool")
            elif pool:
                selected.extend(pool)
                logger.warning(f"  Only {len(pool)} entries remained to fill shortfall")

        return sorted(selected)


# ============================================================================
# SEEDED MULTI-PASS SELECTOR
# ============================================================================

class SeededMultiPassSelector:
    """
    Selects transformation candidates using deterministic seeded randomness
    combined with lineage exclusions for cross-build diversity.
    """

    def __init__(self, seed: int,
                 lineage_tracker: Optional[LineageTracker] = None):
        self.seed = seed
        self.lineage = lineage_tracker or LineageTracker()
        self.rng = random.Random(seed)

        # Per-category sub-seeds for independent streams
        self.pass_seeds = {
            "ZEROING":    self._derive_seed("zeroing"),
            "MOV":        self._derive_seed("mov"),
            "COMPARISON": self._derive_seed("comparison"),
            "ARITHMETIC": self._derive_seed("arithmetic"),
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def select_candidate(self, entry: Dict, semantic_id: str,
                         build_id: str) -> Tuple[Optional[Dict], int]:
        """
        Choose the best safe candidate for *entry*, avoiding recently-used
        choices from lineage history.

        Returns (selected_candidate_dict, choice_index) or (None, -1).
        """
        candidates = entry.get("candidates", [])
        if not candidates:
            return None, -1

        # Safety filter
        safe = [(i, c) for i, c in enumerate(candidates)
                if c.get("safety_score", 0) >= 0.95]
        if not safe:
            logger.warning(f"No safe candidates for {semantic_id}")
            return None, -1

        # Lineage exclusion
        excluded = self.lineage.get_excluded_choices(semantic_id)
        available = [(i, c) for i, c in safe if i not in excluded] or safe

        # Seeded weighted selection
        entry_seed = self._derive_seed(f"{semantic_id}:{self.seed}")
        rng = random.Random(entry_seed)
        weights = [c.get("safety_score", 1.0) for _, c in available]
        total_w = sum(weights)

        choice_idx, choice = available[-1]
        if total_w > 0:
            r = rng.uniform(0, total_w)
            cumulative = 0.0
            for idx, (i, c) in enumerate(available):
                cumulative += weights[idx]
                if r <= cumulative:
                    choice_idx, choice = i, c
                    break

        # Persist to lineage
        self.lineage.record_choice(
            semantic_id=semantic_id,
            seed=self.seed,
            choice_idx=choice_idx,
            bytes_produced=choice.get("proposed_bytes", ""),
            build_id=build_id,
        )

        return choice, choice_idx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _derive_seed(self, component: str) -> int:
        h = hashlib.sha256(f"{self.seed}:{component}".encode())
        return int(h.hexdigest()[:16], 16)


# ============================================================================
# TRANSFORMATION EXECUTOR  (v3.0 — two-pass)
# ============================================================================

class TransformationExecutor:
    """
    Orchestrates the binary transformation pipeline (Instruction Substitution).

    Pass 1  — Instruction substitution
                Size-preserving; patches bytes in-place.

    Diversification options
    -----------------------
    use_divide_transform : bool
        Distribute transformation slots across categories via
        DivideAndTransformAllocator.
    use_lineage : bool
        Use SeededMultiPassSelector + LineageTracker to avoid repeating
        candidate choices from previous builds.
    vary_allocations : bool
        Perturb category percentages by ±10 % using the active seed.
    """

    def __init__(
        self,
        target_count: Optional[int] = None,
        random_seed: Optional[int] = None,
        use_divide_transform: bool = False,
        use_lineage: bool = False,
        vary_allocations: bool = False,
        build_id: Optional[str] = None,
    ):
        self.target_count = target_count
        self.use_divide_transform = use_divide_transform
        self.use_lineage = use_lineage
        self.vary_allocations = vary_allocations
        self.applied_count = 0

        # Auto-generate seed when distribution diversity is requested
        if (use_divide_transform or vary_allocations) and random_seed is None:
            random_seed = int(time.time() * 1_000_000) % (2 ** 32)
            logger.info(f"Auto-generated diversity seed: {random_seed}")

        self.random_seed = random_seed
        self.build_id = build_id or f"{timestamp}_{random_seed or 'noseed'}"

        # Seed global RNG *before* any allocation objects are constructed
        if random_seed is not None:
            random.seed(random_seed)
            logger.info(f"Seeded random generator: {random_seed}")

        # ---- Pass-1 components ----------------------------------------
        self.allocator: Optional[DivideAndTransformAllocator] = None
        self.selector: Optional[SeededMultiPassSelector] = None

        if use_divide_transform:
            allocs = None
            if vary_allocations and random_seed is not None:
                base = DivideAndTransformAllocator()
                allocs = base.vary_allocations(random_seed)
            self.allocator = DivideAndTransformAllocator(allocs)

        if use_lineage:
            self.selector = SeededMultiPassSelector(random_seed or 0)

    # ====================================================================
    # Plan loading
    # ====================================================================

    def load_plan(self, plan_path: Path) -> Tuple[List[Dict], int]:
        """
        Load a v3.0 unified plan file.

        Returns
        -------
        instruction_plan : list[dict]
            Pass-1 instruction substitution specs.
        available_count : int
            Number of AVAILABLE instruction transforms.
        """
        if not plan_path.exists():
            raise FileNotFoundError(f"Plan file not found: {plan_path}")

        try:
            with open(plan_path, "r") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in plan file: {exc}") from exc

        instruction_plan: List[Dict] = data.get("instruction_plan", [])

        # Legacy single-section plans
        if not instruction_plan:
            legacy = data.get("plan", [])
            if legacy:
                logger.warning("Detected legacy plan format — treating as instruction_plan only")
                instruction_plan = legacy
            else:
                raise ValueError("Plan file contains no transformation entries")

        metadata = data.get("metadata", {})
        available_count: int = metadata.get("available_transformations", 0)

        if available_count == 0:
            logger.warning("No available instruction transforms reported in plan metadata")

        logger.info(
            f"Loaded plan: {len(instruction_plan)} instructions, " 
            f"{available_count} available transforms"
        )

        return instruction_plan, available_count

    # ====================================================================
    # Top-level execution
    # ====================================================================

    def execute(
        self,
        instruction_plan: List[Dict],
        available_count: int,
        original_bytes: bytes,
    ) -> Tuple[List[AppliedTransform], bytes]:
        """
        Run the transformation pipeline.

        Returns
        -------
        results    : list[AppliedTransform]  — per-instruction outcome records
        final_bytes: bytes                   — fully transformed binary image
        """
        logger.info("=" * 70)
        logger.info("Starting Instruction Substitution")
        logger.info("=" * 70)

        # Pass 1 ── instruction substitution (size-preserving)
        logger.info("PASS 1: Instruction Substitution")
        modified_bytes, results = self._pass_instruction_substitution(
            instruction_plan, available_count, original_bytes
        )

        return results, modified_bytes

    # ====================================================================
    # Pass 1 — instruction substitution
    # ====================================================================

    def _pass_instruction_substitution(
        self, plan: List[Dict], available_count: int, data: bytes
    ) -> Tuple[bytes, List[AppliedTransform]]:
        """
        In-place, size-preserving instruction replacement.
        Applies self.target_count substitutions (auto-determined if None).
        """
        # Resolve target count
        if self.target_count is None:
            if self.use_divide_transform:
                subset_pct = random.uniform(0.70, 0.95)
                self.target_count = int(available_count * subset_pct)
                logger.info(
                    f"Divide & Transform mode: targeting "
                    f"{self.target_count}/{available_count} ({subset_pct:.1%})"
                )
            else:
                self.target_count = available_count
                logger.info(f"Targeting all {available_count} available transforms")

        if self.target_count > available_count:
            logger.warning(
                f"Requested {self.target_count} but only {available_count} available — "
                f"capping at {available_count}"
            )
            self.target_count = available_count

        if self.target_count <= 0:
            logger.warning("No instruction substitutions to apply")
            return data, self._build_skipped_results(plan)

        # Select indices
        logger.info(f"Selecting {self.target_count} transformations …")
        if self.allocator:
            selected_indices = set(self.allocator.allocate_transformations(plan, self.target_count))
        else:
            available = [i for i, p in enumerate(plan) if p.get("status") == "AVAILABLE"]
            selected_indices = set(random.sample(available, min(self.target_count, len(available))))

        # Apply
        result = bytearray(data)
        results: List[AppliedTransform] = []
        errors = 0

        for i, entry in enumerate(plan):
            if i in selected_indices and self.applied_count < self.target_count:
                try:
                    semantic_id = f"func_{entry.get('function', 'unknown')}:idx_{i}"
                    applied_t, result = self._apply_single_transform(
                        entry, result, semantic_id
                    )
                    self.applied_count += 1
                    results.append(applied_t)

                    step = max(1, self.target_count // 10)
                    if self.applied_count % step == 0:
                        pct = 100 * self.applied_count / self.target_count
                        logger.info(
                            f"  Progress: [{self.applied_count}/{self.target_count}] ({pct:.1f}%)"
                        )
                except Exception as exc:
                    logger.error(f"  Failed at 0x{entry.get('address', 0):x}: {exc}")
                    errors += 1
                    results.append(AppliedTransform(
                        address=entry.get("address", 0),
                        original_asm=entry.get("original_asm", ""),
                        new_asm=entry.get("original_asm", ""),
                        original_bytes=entry.get("original_bytes", ""),
                        new_bytes=entry.get("original_bytes", ""),
                        applied=False,
                        reason=f"ERROR: {exc}",
                        transform_type="FAILED",
                    ))
            else:
                results.append(AppliedTransform(
                    address=entry.get("address", 0),
                    original_asm=entry.get("original_asm", ""),
                    new_asm=entry.get("original_asm", ""),
                    original_bytes=entry.get("original_bytes", ""),
                    new_bytes=entry.get("original_bytes", ""),
                    applied=False,
                    reason=(
                        "Skipped" if entry.get("status") == "AVAILABLE"
                        else entry.get("reason", "")
                    ),
                    transform_type="NONE",
                ))

        if errors:
            logger.warning(f"  {errors} substitution(s) failed")
        logger.info(f"Pass 1 complete: {self.applied_count} instruction substitutions applied")

        return bytes(result), results

    def _apply_single_transform(
        self, entry: Dict, data: bytearray, semantic_id: str
    ) -> Tuple[AppliedTransform, bytearray]:
        """Patch a single instruction in *data* and return the outcome record."""
        candidates = entry.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates available")

        # Candidate selection
        if self.selector:
            selected, choice_idx = self.selector.select_candidate(
                entry, semantic_id, self.build_id
            )
            if selected is None:
                raise ValueError("No safe candidate after lineage filtering")
        else:
            selected = max(candidates, key=lambda c: c.get("safety_score", 0))
            choice_idx = candidates.index(selected)

        addr: int = entry["address"]
        size: int = entry["size"]
        new_bytes = bytes.fromhex(selected["proposed_bytes"])

        if len(new_bytes) != size:
            raise ValueError(
                f"Size mismatch: expected {size}B, got {len(new_bytes)}B"
            )

        data[addr: addr + size] = new_bytes

        return (
            AppliedTransform(
                address=addr,
                original_asm=entry.get("original_asm", ""),
                new_asm=selected.get("proposed_asm", ""),
                original_bytes=entry.get("original_bytes", ""),
                new_bytes=selected["proposed_bytes"],
                applied=True,
                reason=f"Applied {selected.get('type', '?')} (choice {choice_idx})",
                transform_type=selected.get("type", "UNKNOWN"),
            ),
            data,
        )

    def _build_skipped_results(self, plan: List[Dict]) -> List[AppliedTransform]:
        """Return a result list where every entry is marked as skipped."""
        return [
            AppliedTransform(
                address=e.get("address", 0),
                original_asm=e.get("original_asm", ""),
                new_asm=e.get("original_asm", ""),
                original_bytes=e.get("original_bytes", ""),
                new_bytes=e.get("original_bytes", ""),
                applied=False,
                reason="Skipped — no target count",
                transform_type="NONE",
            )
            for e in plan
        ]

    # ====================================================================
    # Persistence
    # ====================================================================

    def save_results(
        self,
        results: List[AppliedTransform],
        final_bytes: bytes,
        output_dir: Path,
        original_exe: Path,
    ) -> None:
        """
        Write the JSON transformation report and the patched binary to
        *output_dir*.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        applied = [r for r in results if r.applied]
        type_counts: Dict[str, int] = defaultdict(int)
        for r in applied:
            type_counts[r.transform_type] += 1

        report = {
            "metadata": {
                "requested_count": self.target_count,
                "applied_count": len(applied),
                "success_rate": (
                    len(applied) / self.target_count if self.target_count else 0
                ),
                "strategies_used": {
                    "divide_and_transform": self.use_divide_transform,
                    "lineage_tracking": self.use_lineage,
                    "varied_allocations": self.vary_allocations,
                },
                "type_distribution": dict(type_counts),
                "seed": self.random_seed,
                "build_id": self.build_id,
                "timestamp": timestamp,
            },
            "transformations": [
                {
                    "address":       r.address,
                    "original_asm":  r.original_asm,
                    "new_asm":       r.new_asm,
                    "original_bytes": r.original_bytes,
                    "new_bytes":     r.new_bytes,
                    "applied":       r.applied,
                    "reason":        r.reason,
                    "type":          r.transform_type,
                }
                for r in results
            ],
        }

        json_path = output_dir / "transformation_report.json"
        with open(json_path, "w") as fh:
            json.dump(report, fh, indent=2)

        exe_path = output_dir / f"obfuscated_{original_exe.name}"
        with open(exe_path, "wb") as fh:
            fh.write(final_bytes)

        original_size = original_exe.stat().st_size
        delta = len(final_bytes) - original_size

        logger.info(f"Results saved to {output_dir}")
        logger.info(f"  Report  : {json_path}")
        logger.info(f"  Binary  : {exe_path}")
        logger.info(f"  Size    : {len(final_bytes):,}B ({delta:+,}B vs original)")


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def _parse_allocation_args(args: argparse.Namespace) -> Optional[Dict[str, float]]:
    """Build an allocation dict from the optional percentage flags."""
    mapping = {
        "ZEROING":    args.zeroing_pct,
        "MOV":        args.mov_pct,
        "COMPARISON": args.comparison_pct,
        "ARITHMETIC": args.arithmetic_pct,
    }
    allocations = {k: v / 100.0 for k, v in mapping.items() if v is not None}

    if allocations:
        total = sum(allocations.values())
        if abs(total - 1.0) > 0.05:
            logger.warning(
                f"Custom allocations sum to {total * 100:.1f}% (expected ~100%)"
            )

    return allocations or None


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Transformation Engine v3.0 — Instruction Substitution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Performs size-preserving instruction substitution.

Examples:
  %(prog)s --plan plan.json --exe target.exe -o out/
  %(prog)s --plan plan.json --exe target.exe -o out/ --seed 1234 -d -l
        """,
    )

    # Core
    parser.add_argument("--plan", "-p", required=True, type=Path,
                        help="Path to unified transformation plan (v3.0 JSON)")
    parser.add_argument("--exe", "-e", required=True, type=Path,
                        help="Path to original executable")
    parser.add_argument("--output", "-o", required=True, type=Path,
                        help="Output directory (created if absent)")
    parser.add_argument("--count", "-n", type=int, default=None,
                        help="Max instruction substitutions (default: auto)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility (default: auto)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without writing any output files")

    # Divide & Transform
    grp_dt = parser.add_argument_group("Divide & Transform")
    grp_dt.add_argument("--divide-transform", "-d", action="store_true",
                        help="Enable category-based distribution shuffling")
    grp_dt.add_argument("--zeroing-pct", type=float, metavar="PCT",
                        help="Allocation %% for XOR/SUB zeroing patterns")
    grp_dt.add_argument("--mov-pct", type=float, metavar="PCT",
                        help="Allocation %% for MOV variants")
    grp_dt.add_argument("--comparison-pct", type=float, metavar="PCT",
                        help="Allocation %% for TEST/AND comparisons")
    grp_dt.add_argument("--arithmetic-pct", type=float, metavar="PCT",
                        help="Allocation %% for CMP/ADD/SUB arithmetic")
    grp_dt.add_argument("--vary-allocations", action="store_true",
                        help="Perturb allocations by ±10%% per seed")

    # Lineage tracking
    grp_lin = parser.add_argument_group("Lineage Tracking")
    grp_lin.add_argument("--lineage", "-l", action="store_true",
                         help="Avoid candidate choices used in recent builds")
    grp_lin.add_argument("--lineage-db", type=Path, default=Path("lineage.db"),
                         help="Path to lineage SQLite database (default: lineage.db)")

    # Logging
    grp_log = parser.add_argument_group("Logging")
    grp_log.add_argument("--verbose", "-v", action="store_true",
                         help="Enable DEBUG-level output")
    grp_log.add_argument("--quiet", "-q", action="store_true",
                         help="Suppress everything except errors")

    args = parser.parse_args()

    # ---- Logging level --------------------------------------------------
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ---- Input validation -----------------------------------------------
    errors_found = False
    if not args.plan.exists():
        logger.error(f"Plan not found: {args.plan}")
        errors_found = True
    if not args.exe.exists():
        logger.error(f"Executable not found: {args.exe}")
        errors_found = True
    if args.count is not None and args.count < 0:
        logger.error("--count must be non-negative")
        errors_found = True
    if errors_found:
        return 2

    # ---- Load original binary -------------------------------------------
    with open(args.exe, "rb") as fh:
        original_bytes = fh.read()


    # ---- Execute --------------------------------------------------------
    try:
        logger.info("=" * 70)
        logger.info("Transformation Engine v3.0")
        logger.info("=" * 70)

        engine = TransformationExecutor(
            target_count=args.count,
            random_seed=args.seed,
            use_divide_transform=args.divide_transform,
            use_lineage=args.lineage,
            vary_allocations=args.vary_allocations,
            build_id=f"{timestamp}_{args.seed or 'auto'}",
        )

        # Override allocator if explicit percentages were supplied
        if args.divide_transform:
            custom_allocs = _parse_allocation_args(args)
            if custom_allocs:
                logger.info("Applying custom category allocations")
                engine.allocator = DivideAndTransformAllocator(custom_allocs)

        # Load plan
        instruction_plan, available_count = engine.load_plan(args.plan)

        # Execute two-pass transformation
        results, final_bytes = engine.execute(
            instruction_plan=instruction_plan,
            available_count=available_count,
            original_bytes=original_bytes,
        )

        # Persist output
        if not args.dry_run:
            engine.save_results(results, final_bytes, args.output, args.exe)
        else:
            logger.info("Dry run — no output written")

        # ---- Summary ----------------------------------------------------
        applied = [r for r in results if r.applied]
        target = engine.target_count or available_count

        logger.info("=" * 70)
        logger.info("Transformation Summary")
        logger.info("=" * 70)
        logger.info(f"Applied  : {engine.applied_count}/{target}")

        if applied:
            type_dist: Dict[str, int] = defaultdict(int)
            for r in applied:
                type_dist[r.transform_type] += 1
            logger.info("Type distribution:")
            for t, c in sorted(type_dist.items(), key=lambda x: -x[1]):
                logger.info(f"  • {t}: {c} ({100 * c / len(applied):.1f}%)")

        logger.info("=" * 70)

        success = engine.applied_count == target
        if success:
            logger.info("Transformation completed successfully")
            return 0
        else:
            logger.warning("Transformation completed with warnings")
            return 1

    except FileNotFoundError as exc:
        logger.error(f"File not found: {exc}")
        return 2
    except ValueError as exc:
        logger.error(f"Invalid input: {exc}")
        return 2
    except Exception as exc:
        logger.error(f"Execution failed: {exc}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())