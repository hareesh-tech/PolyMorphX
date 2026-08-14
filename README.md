# PolyMorph — Signature Randomizer for Executables

**A modular, deterministic framework for semantics-preserving polymorphic transformation of 64-bit Windows PE files.**

PolyMorph rewrites and rebuilds Portable Executable (PE) binaries so that each output is
**byte-distinct and structurally distinct** from the original, while its **runtime behaviour is
provably preserved**. It is built for controlled research into binary diversification and the
robustness of signature-based detection.

> ⚠️ **Intended for authorized security research and educational use only.** Run it against
> binaries you own or are permitted to analyze.

---

## Key properties

- **Semantics-preserving** — every transformation keeps register/flag results identical.
- **Byte-size invariant** — replacement bytes always equal the original instruction size.
- **Control-flow safe** — branches, RIP-relative access, syscalls, SEH and stack frames are never touched.
- **Deterministic & reproducible** — randomness is seed-driven, so a seed regenerates a variant exactly.
- **Gated pipeline** — every candidate passes safety checks before it is applied; unsafe ones stay untouched.

---

## Architecture — a 7-stage gated pipeline

```
Input PE (.exe / .dll)
      │
      ▼
1. parser_and_extractor   → validate PE, parse headers, extract .text
      ▼
2. disassembler           → x86-64 disassembly (Capstone)
      ▼
3. transformation_plan    → mark AVAILABLE / PROTECTED, score candidates
      ▼
4. transformation         → apply semantics-preserving substitutions (Keystone)
      ▼
5. binary_patcher         → patch .text in place
      ▼
6. cfg_permutator         → swap safe basic blocks (layout randomization, LIEF)
      ▼
7. signature_randomizer   → entry-point trampoline + signature scramble
      ▼
Transformed PE  (+ per-stage JSON artifacts)
```

`orchestrator.py` reads `modules/config.json` and runs each stage in order, resolving
placeholders (base path, input name, output dir, seed) and streaming logs.

---

## Repository structure

```
PolyMorphX/
├── modules/                     # Core engine (the 7 pipeline stages + orchestrator)
│   ├── orchestrator.py          #   config-driven driver
│   ├── parser_and_extractor.py  #   stage 1
│   ├── disassembler.py          #   stage 2
│   ├── transformation_plan.py   #   stage 3
│   ├── transformation.py        #   stage 4
│   ├── binary_patcher.py        #   stage 5
│   ├── cfg_permutator.py        #   stage 6
│   ├── signature_randomizer.py  #   stage 7
│   ├── junk_generator.py        #   register-neutral padding generator
│   ├── assembler_bridge.py      #   Keystone assembly helper
│   └── config.json              #   pipeline definition
├── ControlFlowGraph/
│   └── entrypoint_randomizer.py # CFG entry-point diversification support
├── utility_tools/               # Validation / comparison utilities
│   ├── exe_tools/
│   │   ├── compare_exes.py       #   byte-level original-vs-variant report
│   │   ├── signature_comparison.py
│   │   └── transform_comparison.py
│   └── cfg_tools/
│       └── cfg_comparison.py
├── web/                         # Web console (drives the same engine over HTTP)
│   ├── backend/                 #   FastAPI + Uvicorn + WebSocket streaming
│   └── frontend/                #   React 19 + Vite + TypeScript + Tailwind + Recharts
├── MultipleTransformationPlan.md# Design notes on transformation strategies
├── requirements.txt             # Engine Python dependencies
└── README.md
```

---

## Requirements

- Python 3.8+
- Engine libraries: **Capstone** (disassembly), **Keystone** (assembly), **pefile** (PE parsing), **LIEF** (section analysis)
- Web console: **Node.js 18+** (frontend) and the backend Python deps in `web/backend/requirements.txt`

---

## Installation

### Engine (CLI)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Web console (optional)

```bash
# backend
cd web/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# frontend
cd ../frontend
npm install
```

---

## Usage

### 1. Command line (orchestrator)

```bash
cd modules
python orchestrator.py \
    --input  /path/to/target.exe \
    --config config.json \
    --output ./Output \
    --cfg-seed 1234 -v
```

Outputs (`step_01…step_07` binaries plus per-stage JSON) are written to the `--output` directory.

**Options**

| Option                | Description                                        |
| --------------------- | -------------------------------------------------- |
| `--input`             | Input PE file path                                 |
| `--config`            | Pipeline configuration file (`config.json`)        |
| `--output`            | Output directory                                   |
| `--count`             | Max number of instruction transformations          |
| `--cfg-count`         | Max number of CFG-safe block swaps                 |
| `--cfg-enable-subset` | Intelligent subset selection for block swaps        |
| `--cfg-subset-pct`    | Manual subset percentage (0.0–1.0)                 |
| `--cfg-seed`          | Deterministic seed for reproducible builds          |
| `--divide-transform`  | Distribution shuffling across instruction types     |
| `-v` / `-q`           | Verbose / quiet logging                            |

> You supply your own PE binary as input — no sample binaries are bundled with this repository.

### 2. Web console

```bash
# terminal 1 — backend (engine deps must be importable; set POLYMORPH_PYTHON if needed)
cd web/backend
POLYMORPH_PYTHON=$(which python) uvicorn app.main:app --reload --port 8123

# terminal 2 — frontend
cd web/frontend
npm run dev
```

Open the Vite URL (default `http://localhost:5173`). Upload a binary, set options/seed, and
**Launch Transformation** — the backend runs `orchestrator.py` as a subprocess and streams live
pipeline progress, a console, an analytics dashboard, and downloadable artifacts. See
[`web/README.md`](web/README.md) for details.

---

## Transformation techniques

All instruction substitutions are semantics-preserving and byte-size invariant:

| Class                     | Example                                   |
| ------------------------- | ----------------------------------------- |
| **Register zeroing**      | `xor reg,reg` ↔ `sub reg,reg`             |
| **MOV encoding swap**     | opcode `0x89` ↔ `0x8B` (register-direct)  |
| **TEST ↔ AND**            | `test reg,reg` ↔ `and reg,reg`            |
| **CMP ↔ SUB (with 0)**    | `cmp reg,0` ↔ `sub reg,0`                 |

Plus layout-level diversification: **junk-code insertion** (register-neutral padding),
**safe basic-block swapping**, **CFG structural permutation**, and **entry-point / signature
randomization** via code-cave trampolining.

**Never transformed (PROTECTED):** control flow (`jmp/call/ret`/branches), RIP-relative access,
system instructions (`syscall/int`), frame pointer (`push rbp; mov rbp,rsp`), TEB access, and the
entry zone.

---

## Validation

After a run, compare the original against the final variant:

```bash
cd utility_tools/exe_tools
python compare_exes.py --original /path/to/original.exe \
                       --transformed /path/to/step_07_*_signature_randomized.exe
```

`compare_exes.py` reports byte similarity, entry-point change, section entropy, and opcode drift.
`signature_comparison.py`, `transform_comparison.py`, and `cfg_tools/cfg_comparison.py` provide
signature, instruction, and control-flow comparisons respectively.

---

## Safety model

PolyMorph follows a **zero-tolerance destabilization policy**: no stack-pointer manipulation, no
branch relocation, no instruction resizing, no cross-block semantic rewriting, and no SEH-chain
modification. Every transformation is deterministically validated, policy-gated, size-preserving,
and reproducible when the seed is retained.
