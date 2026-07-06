# PolyMorph

###  Binary Analysis &  Transformation Framework

---

## Executive Summary

**PolyMorph** is a modular tool designed to transform and rebuild executables, engineered for the controlled analysis of software protection mechanisms, binary polymorphism, and execution behavior. PolyMorph provides a robust pipeline for transforming Portable Executable (PE) files while maintaining structural integrity and execution stability.

---

# Key Features

* Structural integrity
* Runtime stability
* Control-flow correctness
* Exception handling reliability

PolyMorph is engineered for **safe polymorphism experimentation**, **binary diversification research**, and **execution behavior analysis** within controlled environments.

---

# Key Capabilities

### Deterministic Transformation Pipeline

Each transformation is validated before execution through a structured, multi-stage gating process.

### Safety-First Design

Every transformation candidate is:

* Semantics-preserving
* Byte-size preserving
* Stack-safe
* Control-flow neutral
* Audited against policy constraints

### Modular Architecture

The framework is divided into independently verifiable modules for ingestion, disassembly, transformation planning, execution, and binary patching.

### Reproducible Builds

Seed-based randomness ensures controlled, repeatable diversification.

---

# High-Level Architecture

PolyMorph operates as a deterministic gated pipeline:

```
Input Artifact
      │
      ▼
Parse, Validate & Extract
      │
      ▼
Disassembly & Analysis
      │
      ▼
Transformation Planning
      │
      ▼
Plan Verification
      │
      ▼
Transformation Engine
      │
      ▼
Binary Patching
      │
      ▼
Transformed Executable
```

Each stage enforces strict validation rules to prevent destabilizing modifications.

---

# Core Pipeline Stages

## 1. Ingestion, Parsing & Extraction

* Validates PE structure using bounds checking
* Parses headers and sections
* Extracts `.text` section for controlled processing
* Detects unsafe regions (entry zones, branch targets, etc.)

## 2. Disassembly & Analysis

* Converts machine code into structured instruction representations
* Identifies control-flow boundaries
* Detects protected instruction classes
* Maps branch targets and sensitive regions

## 3. Transformation Planning

* Generates candidate substitutions
* Evaluates instruction eligibility
* Simulates transformations
* Scores safety and compliance

## 4. Plan Verification

Each candidate is validated against:

* Control-flow integrity rules
* Stack-frame stability policies
* RIP-relative addressing constraints
* Exception handling safety
* Size preservation requirements

## 5. Transformation Execution

* Applies only verified transformations
* Maintains instruction size
* Preserves flags and register semantics

## 6. Reassembly & Binary Patching

* Re-encodes transformed instructions
* Patches `.text` section in place
* Reconstructs executable without altering structure or size

---

# Installation & Requirements

## Prerequisites

* Python 3.8+
* Capstone Engine (Disassembly)
* Keystone Engine (Assembly)
* pefile (PE parsing)

## Setup

```bash
git clone git@internal.repo:security/polymorph.git
cd polymorph
pip install -r requirements.txt
```

---

# Usage

Run the orchestrator:

```bash
python orchestrator.py \
    --input target.exe \
    --config config.json \
    --output Outputpath/output.exe
```

---

# Configuration Options

| Option                | Description                                     |
| --------------------- | ----------------------------------------------- |
| `--count`             | Maximum instruction transformations             |
| `--cfg-count`         | Maximum CFG-safe block swaps                    |
| `--cfg-enable-subset` | Intelligent subset selection for block swaps    |
| `--divide-transform`  | Distribution shuffling across instruction types |
| `--seed`              | Deterministic build seed                        |

---

# Project Structure

```
PolyMorph/
├── modules/
│   ├── parser_and_extractor.py
│   ├── disassembler.py
│   ├── transformation_plan.py
│   ├── transformation.py
│   ├── binary_patcher.py
│   ├── config.json
│   └── orchestrator.py
└── Outputs/
```

---

# Implemented Transformation Classes

All transformations are **semantics-preserving and byte-size invariant**.

---

## 1. Register Zeroing Substitution

### Supported Forms

```
xor reg, reg
sub reg, reg
cmp reg, reg
test reg, reg
```

### Safety Properties

* Zero register result preserved
* Flags preserved where required
* No memory access
* No stack modification
* 100% safe for general-purpose registers

---

## 2. Register-to-Register MOV Encoding Swap

x86-64 supports two equivalent encodings:

| Opcode | Meaning        |
| ------ | -------------- |
| 0x89   | MOV r/m64, r64 |
| 0x8B   | MOV r64, r/m64 |

When `Mod = 11` (register-direct mode), the instruction can be re-encoded without semantic change.

### Strict Safety Rule

* Only `Mod = 11` accepted
* Memory modes excluded
* No displacement allowed

---

## 3. TEST ↔ AND (reg, reg)

```
test eax, eax
and eax, eax
```

### Behavior

* Result identical
* Flags identical
* Register value unchanged
* Size preserved

---

## 4. CMP reg, 0 ↔ SUB reg, 0

Both perform:

```
reg - 0
```

### Guarantees

* Register unchanged
* Flags identical
* 3 bytes preserved
* No memory access
* No stack interaction

High diversification value due to rarity differences in compiler usage.

---

# Explicitly Protected Instructions

The following categories are never transformed:

### Control Flow

* `jmp`
* `call`
* `ret`
* Conditional branches

### RIP-Relative Addressing

* `[rip+disp]` memory access

### System Instructions

* `syscall`
* `int`

### Stack Frame Management

* `push rbp`
* `mov rbp, rsp`

### Exception Handling Sensitive Code

* SEH regions
* Prologue/epilogue zones

---

# Transformation Plan Structure

Each validated instruction entry:

```json
{
  "address": 5368710144,
  "offset": 42,
  "status": "AVAILABLE",
  "original_asm": "xor eax, eax",
  "original_bytes": "31C0",
  "size": 2,
  "reason": "Transformable",
  "candidates": [
    {
      "type": "ZEROING",
      "proposed_asm": "sub eax, eax",
      "proposed_bytes": "29C0",
      "safety_score": 1.0
    }
  ]
}
```

### Status Types

| Status    | Meaning           |
| --------- | ----------------- |
| AVAILABLE | Safe to transform |
| PROTECTED | Never transform   |

### Protection Reasons

* BRANCH_TARGET
* RIP_RELATIVE
* CONTROL_FLOW
* FRAME_POINTER
* TEB_ACCESS
* ENTRY_ZONE

---

# Safe Basic Block Swap Engine

## Overview

PolyMorph includes a **semantics-preserving layout randomization engine** that swaps strictly safe basic blocks within `.text`.

This engine:

* Does not modify instruction bytes
* Does not alter program logic
* Does not change binary size
* Only affects physical layout

---

## Swap Eligibility Rules

A block must:

* Contain no control-flow instructions
* Contain no stack-frame access
* Contain no memory writes
* Be context-independent
* Match another block byte-for-byte
* Be identical in size

---

## What Changes

* Physical ordering of safe blocks
* Virtual addresses of swapped blocks
* Layout-level structure only

Runtime behavior remains identical.

---

# Security & Stability Model

PolyMorph follows a **zero-tolerance destabilization policy**:

* No stack pointer manipulation
* No branch relocation
* No instruction resizing
* No cross-block semantic rewriting
* No SEH chain modification

Every transformation is:

* Deterministically validated
* Policy-gated
* Size-preserving
* Reversible (if seed retained)

---

# Design Philosophy

PolyMorph is intentionally conservative.

It prioritizes:

* Stability over aggressiveness
* Determinism over randomness
* Policy validation over transformation volume

The framework is engineered for **crash-safe experimentation in research environments**.

---

# Future Roadmap

* Dependency-graph-based block relocation
* Cross-basic-block semantic validation
* Function-level safe diversification
* Extended transformation catalog
* Automated transformation auditing reports

---

# Summary

PolyMorph is a deterministic, binary transformation framework delivering:

* Semantics-preserving polymorphism
* Strict safety guarantees
* Layout randomization capabilities
* Reproducible diversification
* Modular validation pipeline

It provides a controlled environment for advanced binary research without compromising execution integrity.
