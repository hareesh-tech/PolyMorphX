#!/usr/bin/env python3
"""
CFG Swap Engine - Intelligent Subset Selection

Strategy:
1. Only swap IDENTICAL instruction sequences
2. Apply intelligent subset based on available swaps:
3. Extensive validation before every swap
"""

import lief
import capstone
import random
import argparse
import sys
import logging
import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set
from pathlib import Path
from enum import Enum
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class BlockCategory(Enum):
    """Categories of blocks by safety level."""
    IDENTICAL_CODE = "identical_code"
    PURE_PADDING = "pure_padding"
    UNSAFE = "unsafe"


@dataclass
class Instruction:
    """Single instruction with metadata."""
    address: int
    bytes: bytes
    mnemonic: str
    op_str: str
    size: int
    
    def __hash__(self):
        return hash(self.address)
    
    def normalize_operands(self) -> str:
        """Normalize operands for comparison."""
        return self.op_str.lower()
    
    def get_semantic_signature(self) -> str:
        """Get signature for semantic comparison."""
        return f"{self.mnemonic.lower()}:{self.normalize_operands()}"


@dataclass
class BasicBlock:
    """Basic block with safety metadata."""
    start_addr: int
    end_addr: int
    instructions: List[Instruction] = field(default_factory=list)
    original_offset: int = 0
    size: int = 0
    category: BlockCategory = BlockCategory.UNSAFE
    semantic_hash: str = ""
    
    def __hash__(self):
        return hash(self.start_addr)
    
    def calculate_semantic_hash(self) -> str:
        """Calculate hash based on instruction semantics."""
        signatures = [insn.get_semantic_signature() for insn in self.instructions]
        combined = "|".join(signatures)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def is_pure_padding(self) -> bool:
        """Check if block is ONLY padding (NOPs, INT3)."""
        if not self.instructions:
            return False
        return all(insn.mnemonic.lower() in ('nop', 'int3') 
                  for insn in self.instructions)
    
    def is_identical_to(self, other: 'BasicBlock') -> bool:
        """Check if two blocks are EXACTLY identical in semantics."""
        if len(self.instructions) != len(other.instructions):
            return False
        
        if self.size != other.size:
            return False
        
        for insn_a, insn_b in zip(self.instructions, other.instructions):
            if insn_a.mnemonic.lower() != insn_b.mnemonic.lower():
                return False
            
            if insn_a.get_semantic_signature() != insn_b.get_semantic_signature():
                return False
        
        return True
    
    def get_instruction_bytes_signature(self) -> str:
        """Get signature of actual bytes."""
        all_bytes = b''.join(insn.bytes for insn in self.instructions)
        return hashlib.sha256(all_bytes).hexdigest()[:16]


class SwapEngine:
    """
    safe swap engine with intelligent subset selection.
    """
    
    def __init__(self, pe: lief.PE.Binary, seed: Optional[int] = None, 
                 enable_subset: bool = False, subset_percentage: Optional[float] = None):
        self.pe = pe
        self.enable_subset = enable_subset
        self.manual_subset_pct = subset_percentage
        
        # Auto-generate seed if not provided
        if seed is None:
            seed = int(time.time() * 1000000) % (2**32)
            logger.info(f"Auto-generated seed: {seed}")
        
        self.seed = seed
        self.rng = random.Random(self.seed)
        
        self.blocks: List[BasicBlock] = []
        self.image_base = pe.optional_header.imagebase
        
        # Initialize Capstone
        self.cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.cs.detail = True
        
        # Find .text section
        self.text_section = None
        for section in pe.sections:
            if section.name.lower() == '.text':
                self.text_section = section
                break
        
        if not self.text_section:
            raise ValueError("No .text section found")
        
        self.text_va_start = self.image_base + self.text_section.virtual_address
        self.text_va_end = self.text_va_start + self.text_section.virtual_size
        self.original_code = bytes(self.text_section.content)
        
        # Entry point
        entry_rva = self.pe.optional_header.addressof_entrypoint
        self.entry_va = self.image_base + entry_rva
        
        logger.info("Initialized CFG swap engine")
        logger.info(f"  Image base: {hex(self.image_base)}")
        logger.info(f"  Text section: {hex(self.text_va_start)} - {hex(self.text_va_end)}")
        logger.info(f"  Entry point: {hex(self.entry_va)}")
        logger.info(f"  Seed: {self.seed}")
        logger.info(f"  Subset mode: {'enabled' if self.enable_subset else 'disabled'}")
    
    def disassemble_block(self, code: bytes, start_va: int) -> List[Instruction]:
        """Disassemble block into instructions."""
        instructions = []
        try:
            for insn in self.cs.disasm(code, start_va):
                instruction = Instruction(
                    address=insn.address,
                    bytes=insn.bytes,
                    mnemonic=insn.mnemonic,
                    op_str=insn.op_str,
                    size=insn.size
                )
                instructions.append(instruction)
        except Exception as e:
            logger.debug(f"Disassembly error at {hex(start_va)}: {e}")
        
        return instructions
    
    def find_basic_blocks(self) -> List[BasicBlock]:
        """Find basic blocks using conservative analysis."""
        logger.info("Finding basic blocks...")
        
        code = self.original_code
        leaders = {self.text_va_start, self.entry_va}
        
        # First pass: find all potential leaders
        try:
            for insn in self.cs.disasm(code, self.text_va_start):
                mnemonic = insn.mnemonic.lower()
                
                # After control flow instruction
                if mnemonic in ('ret', 'retn', 'retf', 'jmp') or mnemonic.startswith('j'):
                    leaders.add(insn.address + insn.size)
                
                # Target of jump
                if mnemonic.startswith('j') or mnemonic == 'call':
                    if insn.op_str.startswith('0x'):
                        try:
                            target = int(insn.op_str, 16)
                            if self.text_va_start <= target < self.text_va_end:
                                leaders.add(target)
                        except ValueError:
                            pass
        except Exception as e:
            logger.warning(f"Error during block analysis: {e}")
        
        # Create blocks
        sorted_leaders = sorted(leaders)
        blocks = []
        
        for i, leader_va in enumerate(sorted_leaders):
            end_va = sorted_leaders[i + 1] if i + 1 < len(sorted_leaders) else self.text_va_end
            
            offset = leader_va - self.text_va_start
            size = end_va - leader_va
            
            if size <= 0 or size > 1000:
                continue
            
            block_code = code[offset:offset + size]
            instructions = self.disassemble_block(block_code, leader_va)
            
            if not instructions:
                continue
            
            block = BasicBlock(
                start_addr=leader_va,
                end_addr=end_va,
                instructions=instructions,
                original_offset=offset,
                size=size
            )
            
            block.semantic_hash = block.calculate_semantic_hash()
            
            if block.is_pure_padding():
                block.category = BlockCategory.PURE_PADDING
            else:
                block.category = BlockCategory.UNSAFE
            
            blocks.append(block)
        
        logger.info(f"Found {len(blocks)} basic blocks")
        return blocks
    
    def find_identical_blocks(self) -> Dict[str, List[BasicBlock]]:
        """Find groups of blocks that are EXACTLY identical."""
        if not self.blocks:
            self.blocks = self.find_basic_blocks()
        
        # Group by semantic hash
        hash_groups = defaultdict(list)
        for block in self.blocks:
            hash_groups[block.semantic_hash].append(block)
        
        # Only keep groups with 2+ identical blocks
        identical_groups = {
            h: blocks for h, blocks in hash_groups.items()
            if len(blocks) >= 2
        }
        
        # Verify blocks are truly identical
        verified_groups = {}
        for h, blocks in identical_groups.items():
            if len(blocks) >= 2:
                reference = blocks[0]
                verified = [reference]
                
                for block in blocks[1:]:
                    if reference.is_identical_to(block):
                        verified.append(block)
                
                if len(verified) >= 2:
                    verified_groups[h] = verified
        
        logger.info(f"Found {len(verified_groups)} groups of identical blocks")
        return verified_groups
    
    def find_safe_padding_swaps(self) -> List[Tuple[BasicBlock, BasicBlock]]:
        """Find pairs of pure padding blocks that can be swapped."""
        padding_blocks = [b for b in self.blocks if b.category == BlockCategory.PURE_PADDING]
        
        # Group by size
        size_groups = defaultdict(list)
        for block in padding_blocks:
            size_groups[block.size].append(block)
        
        # Create pairs
        pairs = []
        for size, blocks in size_groups.items():
            if len(blocks) >= 2:
                for i in range(len(blocks)):
                    for j in range(i + 1, len(blocks)):
                        pairs.append((blocks[i], blocks[j]))
        
        logger.info(f"Padding swap pairs: {len(pairs)}")
        return pairs
    
    def find_safe_identical_swaps(self) -> List[Tuple[BasicBlock, BasicBlock]]:
        """Find pairs of truly identical blocks that can be swapped."""
        identical_groups = self.find_identical_blocks()
        
        pairs = []
        for h, blocks in identical_groups.items():
            for i in range(len(blocks)):
                for j in range(i + 1, len(blocks)):
                    pairs.append((blocks[i], blocks[j]))
        
        logger.info(f"Identical swap pairs: {len(pairs)}")
        return pairs
    
    def calculate_subset_percentage(self, total_available: int) -> float:
        """
        Calculate intelligent subset percentage based on available swaps.
        """
        if self.manual_subset_pct is not None:
            return self.manual_subset_pct
        if total_available >= 20000:
            return 0.015
        if total_available >= 10000:
            return 0.025
        elif total_available >= 1000:
            return 0.015
        elif total_available <= 500:
            return 0.01
        
        else:
            # Random between 5-10% for small counts
            return self.rng.uniform(0.010, 0.012)
    
    def validate_swap_safety(self, block_a: BasicBlock, block_b: BasicBlock) -> bool:
        """Final validation before swap."""
        if block_a.size != block_b.size:
            return False
        
        if len(block_a.instructions) != len(block_b.instructions):
            return False
        
        if block_a.category == BlockCategory.PURE_PADDING and \
           block_b.category == BlockCategory.PURE_PADDING:
            return True
        
        if block_a.is_identical_to(block_b):
            return True
        
        return False
    
    def perform_safe_swaps(self, max_swaps: Optional[int] = None) -> Tuple[bytes, int, List[Tuple[BasicBlock, BasicBlock]]]:
        """Perform safe swaps with intelligent subset selection."""
        # Find all safe swap candidates
        padding_swaps = self.find_safe_padding_swaps()
        identical_swaps = self.find_safe_identical_swaps()
        
        all_candidates = padding_swaps + identical_swaps
        
        if not all_candidates:
            logger.warning("No safe swaps found")
            return self.original_code, 0, []
        
        total_available = len(all_candidates)
        logger.info(f"Total safe candidates: {total_available}")
        logger.info(f"  Padding: {len(padding_swaps)}")
        logger.info(f"  Identical: {len(identical_swaps)}")
        
        # Shuffle for randomness
        self.rng.shuffle(all_candidates)
        
        # Determine target count
        if max_swaps is None:
            if self.enable_subset:
                subset_pct = self.calculate_subset_percentage(total_available)
                max_swaps = int(total_available * subset_pct)
                logger.info(f"Intelligent subset: {max_swaps}/{total_available} ({subset_pct*100:.1f}%)")
            else:
                max_swaps = total_available
                logger.info(f"Applying all available swaps: {max_swaps}")
        else:
            logger.info(f"Using explicit count: {max_swaps}")
        
        # Select non-overlapping swaps
        selected_swaps = []
        used_blocks = set()
        
        for block_a, block_b in all_candidates:
            if block_a in used_blocks or block_b in used_blocks:
                continue
            
            # Final validation
            if not self.validate_swap_safety(block_a, block_b):
                continue
            
            selected_swaps.append((block_a, block_b))
            used_blocks.add(block_a)
            used_blocks.add(block_b)
            
            if len(selected_swaps) >= max_swaps:
                break
        
        logger.info(f"Selected {len(selected_swaps)} validated swaps")
        
        if not selected_swaps:
            return self.original_code, 0, []
        
        # Apply swaps
        new_code = bytearray(self.original_code)
        
        for block_a, block_b in selected_swaps:
            offset_a = block_a.original_offset
            offset_b = block_b.original_offset
            size = block_a.size
            
            content_a = bytes(new_code[offset_a:offset_a + size])
            content_b = bytes(new_code[offset_b:offset_b + size])
            
            new_code[offset_a:offset_a + size] = content_b
            new_code[offset_b:offset_b + size] = content_a
        
        return bytes(new_code), len(selected_swaps), selected_swaps
    
    def apply_to_pe(self, output_path: Path, max_swaps: Optional[int] = None) -> Dict:
        """Apply safe swaps to PE file."""
        try:
            logger.info("=" * 70)
            logger.info("CFG Swap Engine ")
            logger.info("=" * 70)
            
            new_code, num_swaps, swaps = self.perform_safe_swaps(max_swaps)
            
            # Verify size
            if len(new_code) != len(self.original_code):
                logger.error(f"Size changed: {len(self.original_code)} -> {len(new_code)}")
                return {'success': False, 'error': 'Size mismatch'}
            
            # Update section
            self.text_section.content = list(new_code)
            
            # Write output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.pe.write(str(output_path))
            
            # Calculate hashes
            orig_hash = hashlib.sha256(self.original_code).hexdigest()
            new_hash = hashlib.sha256(new_code).hexdigest()
            
            # Build metadata
            metadata = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'seed': self.seed,
                'total_swaps': num_swaps,
                'subset_enabled': self.enable_subset,
                'original_hash': orig_hash,
                'new_hash': new_hash,
                'output_file': str(output_path)
            }
            
            logger.info("")
            logger.info("=" * 70)
            logger.info("RESULTS")
            logger.info("=" * 70)
            logger.info(f"Output: {output_path}")
            logger.info(f"Swaps performed: {num_swaps}")
            logger.info(f"Seed used: {self.seed}")
            logger.info(f"Original hash: {orig_hash[:16]}...")
            logger.info(f"New hash:      {new_hash[:16]}...")
            
            if num_swaps > 0:
                # Categorize swaps
                padding_swaps = sum(1 for a, b in swaps if a.category == BlockCategory.PURE_PADDING)
                code_swaps = len(swaps) - padding_swaps
                
                logger.info("")
                logger.info("Swap breakdown:")
                logger.info(f"  Padding swaps: {padding_swaps}")
                logger.info(f"  Code swaps: {code_swaps}")
                
                # Save metadata
                metadata_path = output_path.parent / 'cfg_swap_metadata.json'
                self._save_metadata(metadata_path, metadata, swaps)
                logger.info(f"Metadata: {metadata_path}")
            
            logger.info("")
            logger.info("CFG swap completed successfully")
            logger.info("=" * 70)
            
            return metadata
        
        except Exception as e:
            logger.error(f"Failed: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def _save_metadata(self, path: Path, metadata: Dict, swaps: List[Tuple[BasicBlock, BasicBlock]]):
        """Save comprehensive metadata to JSON."""
        detailed_metadata = metadata.copy()
        detailed_metadata['swaps'] = [
            {
                'index': i + 1,
                'block_a_addr': hex(a.start_addr),
                'block_b_addr': hex(b.start_addr),
                'size': a.size,
                'type': 'padding' if a.category == BlockCategory.PURE_PADDING else 'code',
                'block_a_asm': [f"{insn.mnemonic} {insn.op_str}".strip() for insn in a.instructions],
                'block_b_asm': [f"{insn.mnemonic} {insn.op_str}".strip() for insn in b.instructions]
            }
            for i, (a, b) in enumerate(swaps)
        ]
        
        with open(path, 'w') as f:
            json.dump(detailed_metadata, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="CFG Swap Engine - Production with Intelligent Subset Selection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    ) 
    parser.add_argument('-i', '--input', required=True, help='Input PE file')

    parser.add_argument('-o', '--output', required=True, help='Output PE file')

    parser.add_argument('-n', '--num-swaps', type=int, default=None, help='Maximum swaps (default: auto-determined)')

    parser.add_argument('--seed', type=int, default=None, help='Random seed (default: auto-generated)')

    parser.add_argument('--enable-subset', action='store_true', help='Enable intelligent subset selection')

    parser.add_argument('--subset-pct', type=float, default=None, help='Manual subset percentage (0.0-1.0)')

    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    parser.add_argument('-q', '--quiet', action='store_true', help='Minimal output')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    # Validate input
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return 1
    
    try:
        logger.info(f"Loading PE: {input_path}")
        pe = lief.PE.parse(str(input_path))
        
        if not pe:
            logger.error("Failed to parse PE file")
            return 1
        
        # Run engine
        engine = SwapEngine(pe, seed=args.seed, 
                           enable_subset=args.enable_subset,
                           subset_percentage=args.subset_pct)
        result = engine.apply_to_pe(output_path, max_swaps=args.num_swaps)
        
        return 0 if result.get('success') else 1
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

