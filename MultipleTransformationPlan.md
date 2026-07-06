# 1. Divide and Transform
- We can divide the amount of transformations applied for each instructions
    eg: XOR <=> SUB  : 25%
        MOV          : 35%
        TEST <=> AND : 30%
        CMP <=> SUB  : 10%
- We have to change the amount of transformation on each execution


# 2. Seeded Multi-Pass Instruction Substitution with Lineage Tracking
Core Concept
Transform individual instructions into semantically equivalent alternatives using a deterministic seed that varies per build. Each applicable instruction site becomes a decision point with 3-5 valid alternatives.

--------------------------------------------------------------------------------------------------------------------
|   Pattern     |            Alternatives                    |             Safety Constraints                      |
| ------------- | ------------------------------------------ | --------------------------------------------------- |
| `XOR reg,reg` | `SUB reg,reg`, `MOV reg,0`, `LEA reg,[0]`  | Next 5 instructions must not read AF                |
| `CMP reg,0`   | `TEST reg,reg`, `SUB reg,0`, `AND reg,0`   | Branch target within 10 instr must not depend on CF |
| `MOV reg,reg` | `LEA reg,[reg]`, `PUSH/POP`, `XCHG` (self) | Destination not used in RIP-relative in next block  |
| `ADD reg,imm` | `SUB reg,-imm`, `LEA reg,[reg+imm]`        | Overflow flag not live                              |
--------------------------------------------------------------------------------------------------------------------
# Multi-Pass Strategy
Each pass focuses on specific pattern categories to avoid conflicts:
    Pass 1: Zeroing idioms (XOR/SUB/MOV/LEA for zero)
    Pass 2: Comparisons (CMP/TEST/AND for zero-check)
    Pass 3: Data movement (MOV/LEA/XCHG for copies)
    Pass 4: Arithmetic (ADD/SUB/LEA for addition)
    Pass 5: NOP diversification (padding insertion)

# Lineage Tracking Database
Maintain persistent storage of transformation history:
Table: transformation_lineage
- semantic_id: FUNCTION_HASH + INSTRUCTION_INDEX (stable across rebuilds)
- build_timestamp: When this variant was generated
- seed_used: The diversification seed for this build
- choice_made: Which alternative was selected (0-4)
- bytes_produced: The actual byte sequence emitted
- hamming_distance_to_prev: Distance from previous build's choice

Before selecting a transformation, query recent history and exclude choices that are:
    - Identical to last 2 builds (exact byte match)
    - 80% similar to any of last 5 builds (Hamming distance < 20%)
If all safe options are excluded, select the least-similar historical alternative.

# Safety Verification Pipeline
For each candidate substitution:

    Syntax validation: Ensure replacement bytes decode to valid instruction
    Length check: Verify total bytes (including padding) equals original
    Flag liveness analysis: Forward scan until all written flags are overwritten or hit control flow barrier
    Register liveness: Ensure replacement doesn't clobber live registers
    Symbolic equivalence: Use Z3 or similar to prove: ∀inputs, original_output = replacement_output
    Differential test: Execute both on sample inputs, compare final state

Any failure rejects the candidate; if no candidates remain, instruction is protected (unchanged).
Operational Parameters

---------------------------------------------------------------------------------------------------------------------------------
| Parameter                | Production Value | Rationale                                                                       |
| ------------------------ | ---------------- | ------------------------------------------------------------------------------- |
| Max passes               | 5-7              | Diminishing returns beyond 7; entropy plateaus                                  |
| Substitution probability | 0.6-0.8          | 60-80% of applicable sites transformed; balance diversity vs. verification cost |
| Safety score threshold   | 0.95             | Only "very safe" transformations applied automatically                          |
| Lineage lookback         | 5-10 builds      | Prevent recent repetition while allowing long-term cycles                       |
---------------------------------------------------------------------------------------------------------------------------------

#  3. CFG Structural Permutation

- CFG Structural Permutation Enables Unique but Functionally Identical Executables
Core Idea:
A Control Flow Graph (CFG) represents a program as basic blocks (linear instruction sequences) connected by branch edges.
CFG structural permutation changes the layout and branching structure of these blocks without changing execution semantics.

- This means:
    - The program executes the same logic
    - But the binary structure and layout differ
    - Producing multiple unique variants of the same executable

- This Creates Uniqueness Across Executable Instances

- Two executables compiled from the same source normally share:
    -Identical block order
    -Identical branch layout
    -Identical graph structure

- CFG permutation reshapes the program’s structural form by:
    - Reordering basic blocks
    - Rewriting branch edges
    - Inverting conditional branches
    - Injecting deterministic opaque control paths

- As a result:
    - The control-flow shape changes
    - The binary layout changes
    - The hash and structural fingerprint differ
    - But every valid execution path remains identical

- Thus: 
    Same logic, different structure, different binary identity