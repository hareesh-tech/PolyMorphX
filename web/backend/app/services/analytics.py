"""Turns the PolyMorph engine's own output artifacts (transformation plan,
transformation report, CFG swap metadata) into aggregate numbers the frontend
can chart. Everything here is read from files the engine already writes —
nothing is computed by re-running or guessing at the binary.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from .job_manager import Job


def _load_config_techniques(config_path: Path) -> list[dict]:
    try:
        data = json.loads(config_path.read_text())
        return data.get("modules", {}).get("start", {}).get("techniques", [])
    except Exception:
        return []


def _resolve(text: Any, ctx: dict) -> Any:
    if not isinstance(text, str):
        return text
    for key, value in ctx.items():
        text = text.replace(f"{{{key}}}", str(value))
    return text


def _stage_output_paths(job: Job) -> dict[str, Path]:
    """Map stage name -> resolved output file path, using the same
    placeholder substitution the orchestrator applies to config.json.
    """
    ctx = {"input_name": Path(job.input_path).stem if job.input_path else ""}
    mapping: dict[str, Path] = {}
    for technique in _load_config_techniques(job.config_path):
        stage = Path(technique["path"]).stem
        output_file = technique.get("parameters", {}).get("output_file")
        if output_file:
            mapping[stage] = job.output_dir / _resolve(output_file, ctx)
    return mapping


def _read_json(path: Optional[Path]) -> Optional[dict]:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _safety_score_histogram(scores: list[float]) -> list[dict]:
    if not scores:
        return []
    buckets = Counter()
    for score in scores:
        bucket = f"{min(0.99, max(0.0, round(score, 2) - 0.02)):.2f}-{round(score, 2):.2f}"
        buckets[bucket] += 1
    return [{"bucket": b, "count": c} for b, c in sorted(buckets.items())]


def build_analytics(job: Job) -> dict:
    files = _stage_output_paths(job)
    result: dict = {}

    plan = _read_json(files.get("transformation_plan"))
    if plan:
        meta = plan.get("metadata", {})
        entries = plan.get("instruction_plan", [])
        protected_reasons = Counter(
            e.get("reason", "UNKNOWN") for e in entries if e.get("status") == "PROTECTED"
        )
        safety_scores = [
            c.get("safety_score", 0.0)
            for e in entries
            if e.get("status") == "AVAILABLE"
            for c in e.get("candidates", [])
        ]
        result["plan"] = {
            "total_instructions": meta.get("total_instructions", len(entries)),
            "available": meta.get("available_transformations", 0),
            "protected": meta.get("protected_instructions", 0),
            "protected_reasons": dict(protected_reasons),
            "safety_score_histogram": _safety_score_histogram(safety_scores),
        }

    report = _read_json(files.get("transformation"))
    if report:
        meta = report.get("metadata", {})
        transforms = report.get("transformations", [])
        applied = [t for t in transforms if t.get("applied")]
        result["transform"] = {
            "requested": meta.get("requested_count", 0),
            "applied": meta.get("applied_count", len(applied)),
            "success_rate": meta.get("success_rate", 0.0),
            "type_distribution": meta.get("type_distribution", {}),
            "address_map": [
                {"address": t["address"], "type": t.get("type", "UNKNOWN")}
                for t in applied[:3000]
            ],
        }

    cfg_meta_path = job.output_dir / "cfg_swap_metadata.json"
    cfg = _read_json(cfg_meta_path)
    if cfg:
        swaps = cfg.get("swaps", [])
        padding_swaps = sum(1 for s in swaps if s.get("type") == "padding")
        result["cfg"] = {
            "total_swaps": cfg.get("total_swaps", len(swaps)),
            "seed": cfg.get("seed"),
            "subset_enabled": cfg.get("subset_enabled"),
            "padding_swaps": padding_swaps,
            "code_swaps": len(swaps) - padding_swaps,
            "pairs": [
                {
                    "a": int(s["block_a_addr"], 16),
                    "b": int(s["block_b_addr"], 16),
                    "size": s.get("size", 0),
                    "type": s.get("type", "code"),
                }
                for s in swaps[:2000]
            ],
        }

    stage_durations = [
        {
            "stage": s.name,
            "seconds": round((s.completed_at - s.started_at).total_seconds(), 3),
        }
        for s in job.stages
        if s.started_at and s.completed_at
    ]
    if stage_durations:
        result["stage_durations"] = stage_durations

    if job.input_path and job.input_path.exists():
        result["binary"] = {"original_size": job.input_path.stat().st_size}

    return result
