#!/usr/bin/env python3
"""
Junk Generator Service
Generates actual x86-64 machine code bytes on demand.
Called by TransformationEngine during block transformation.
"""

import random
import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum, auto

try:
    from keystone import *
except ImportError:
    raise ImportError("Keystone engine required: pip install keystone-engine")

from transformation_plan import JunkSpec  # Import spec for type hints

logger = logging.getLogger(__name__)


class JunkStrategy(Enum):
    """Available junk code generation strategies."""
    XOR_PAIR = "xor_pair"
    ADD_SUB = "add_sub"
    ROL_ROR = "rol_ror"
    NOT_NOT = "not_not"
    INC_DEC = "inc_dec"
    NEG_NEG = "neg_neg"
    PUSH_POP = "push_pop"


class JunkGenerator:
    """
    Service class that generates junk code bytes ON DEMAND.
    
    This is instantiated by the Orchestrator and injected into
    the TransformationEngine. The engine calls generate_for_spec()
    when it needs actual bytes for a specific block.
    """
    
    # All 64-bit registers that are safe to stomp (caller-saved or scratch)
    SAFE_REGISTERS = ['rax', 'rcx', 'rdx', 'rbx', 'r8', 'r9', 'r10', 'r11']
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, seed: Optional[int] = None):
        self.config = config or {}
        if seed is not None:
            random.seed(seed)
        self.ks = Ks(KS_ARCH_X86, KS_MODE_64)
        self._cache: Dict[str, bytes] = {}
        self.stats = {
            "total_bytes_generated": 0,
            "sequences_generated": 0,
            "cache_hits": 0
        }
        logger.info("JunkGenerator initialized")
    
    def generate_for_block(self, spec: Dict[str, Any]) -> Tuple[bytes, bytes]:
        """
        Generate junk code bytes based on a JunkSpec dict.
        
        This is the main entry point called by TransformationEngine.
        Returns (pre_junk, post_junk) based on spec.position.
        
        Args:
            spec: JunkSpec dict from TransformationPlan
            
        Returns:
            Tuple of (pre_junk_bytes, post_junk_bytes)
        """
        pre_junk = b''
        post_junk = b''
        
        # Handle dict access since plan is loaded from JSON
        position = spec.get("position", "both")
        size_min = spec.get("size_min", 4)
        size_max = spec.get("size_max", 16)
        safe_registers = spec.get("safe_registers", self.SAFE_REGISTERS)
        strategy_weights = spec.get("strategy_weights", {})
        block_addr = spec.get("block_start_addr", 0)
        
        if position in ["pre", "both"]:
            size = random.randint(size_min, size_max)
            pre_junk = self._generate_block(
                size=size,
                safe_registers=safe_registers,
                strategy_weights=strategy_weights
            )
            logger.debug(f"Block 0x{block_addr:x}: Generated {len(pre_junk)} bytes pre-junk")
        
        if position in ["post", "both"]:
            size = random.randint(size_min, size_max)
            post_junk = self._generate_block(
                size=size,
                safe_registers=safe_registers,
                strategy_weights=strategy_weights
            )
            logger.debug(f"Block 0x{block_addr:x}: Generated {len(post_junk)} bytes post-junk")
        
        self.stats["total_bytes_generated"] += len(pre_junk) + len(post_junk)
        self.stats["sequences_generated"] += 1
        
        return pre_junk, post_junk
    
    def _generate_block(self, 
                       size: int, 
                       safe_registers: List[str],
                       strategy_weights: Dict[str, float]) -> bytes:
        """
        Generate a junk block of approximately 'size' bytes.
        
        Uses reversible operations to ensure mathematical soundness.
        """
        current_size = 0
        sequences = []
        
        while current_size < size:
            # Select strategy based on weights
            strategy = self._select_strategy(strategy_weights)
            
            # Select register from safe list
            reg = random.choice(safe_registers)
            
            # Generate sequence
            seq = self._generate_sequence(strategy, reg)
            
            # Avoid oversized sequences
            if current_size + len(seq) > size * 1.5 and sequences:
                break
            
            sequences.append(seq)
            current_size += len(seq)
        
        return b''.join(sequences)
    
    def _select_strategy(self, weights: Dict[str, float]) -> JunkStrategy:
        """Select strategy based on weight distribution."""
        strategies = list(JunkStrategy)
        weight_values = [weights.get(s.value, 0.1) for s in strategies]
        return random.choices(strategies, weights=weight_values)[0]
    
    def _generate_sequence(self, strategy: JunkStrategy, reg: str) -> bytes:
        """Generate a single reversible instruction sequence."""
        generators = {
            JunkStrategy.XOR_PAIR: self._gen_xor,
            JunkStrategy.ADD_SUB: self._gen_add_sub,
            JunkStrategy.ROL_ROR: self._gen_rol_ror,
            JunkStrategy.NOT_NOT: self._gen_not,
            JunkStrategy.INC_DEC: self._gen_inc_dec,
            JunkStrategy.NEG_NEG: self._gen_neg,
            JunkStrategy.PUSH_POP: self._gen_push_pop,
        }
        return generators[strategy](reg)
    
    def _assemble(self, asm: str) -> bytes:
        """Assemble instruction using Keystone with caching."""
        if asm in self._cache:
            self.stats["cache_hits"] += 1
            return self._cache[asm]
        
        try:
            encoding, _ = self.ks.asm(asm)
            if encoding is None:
                raise ValueError(f"Assembly failed: {asm}")
            result = bytes(encoding)
            self._cache[asm] = result
            return result
        except KsError as e:
            logger.error(f"Keystone error assembling '{asm}': {e}")
            return b'\x90'  # NOP fallback
    
    # Individual generators (reversible operations)
    def _gen_xor(self, reg: str) -> bytes:
        """XOR with immediate, twice (self-inverse)."""
        imm = random.getrandbits(31)
        instr = self._assemble(f"xor {reg}, {hex(imm)}")
        return instr + instr  # XOR twice = identity
    
    def _gen_add_sub(self, reg: str) -> bytes:
        """ADD then SUB with same immediate."""
        imm = random.randint(1, 0x7FFFFFFF)
        add = self._assemble(f"add {reg}, {hex(imm)}")
        sub = self._assemble(f"sub {reg}, {hex(imm)}")
        return add + sub
    
    def _gen_rol_ror(self, reg: str) -> bytes:
        """Rotate left then right."""
        imm = random.randint(1, 63) if reg.startswith('r') else random.randint(1, 31)
        rol = self._assemble(f"rol {reg}, {imm}")
        ror = self._assemble(f"ror {reg}, {imm}")
        return rol + ror
    
    def _gen_not(self, reg: str) -> bytes:
        """NOT twice (self-inverse)."""
        instr = self._assemble(f"not {reg}")
        return instr + instr
    
    def _gen_inc_dec(self, reg: str) -> bytes:
        """INC then DEC (or reverse)."""
        inc = self._assemble(f"inc {reg}")
        dec = self._assemble(f"dec {reg}")
        return (inc + dec) if random.choice([True, False]) else (dec + inc)
    
    def _gen_neg(self, reg: str) -> bytes:
        """NEG twice (double negation = original)."""
        instr = self._assemble(f"neg {reg}")
        return instr + instr
    
    def _gen_push_pop(self, reg: str) -> bytes:
        """PUSH then POP (stack-based preservation)."""
        push = self._assemble(f"push {reg}")
        pop = self._assemble(f"pop {reg}")
        return push + pop
    
    def get_stats(self) -> Dict[str, Any]:
        """Return generation statistics."""
        stats = self.stats.copy()
        # Add aliases expected by TransformationEngine
        stats["blocks_processed"] = stats["sequences_generated"]
        stats["bytes_generated"] = stats["total_bytes_generated"]
        return stats