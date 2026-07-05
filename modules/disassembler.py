#!/usr/bin/env python3
"""
EXE Disassembler - .text section disassembly for EXE analysis
Supports auto-architecture detection, Capstone disassembly, dual JSON/text output.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Import reusable components from parser_and_extractor

from parser_and_extractor import setup_logging
import capstone
import pefile
PE_FILE_AVAILABLE = True
    


class ArchitectureDetector:
    """Detect binary architecture using multiple strategies."""
    
    # PE Machine types
    MACHINE_X86 = 0x14c
    MACHINE_X64 = 0x8664
    
    # REX prefix range for x64 detection
    REX_PREFIX_START = 0x40
    REX_PREFIX_END = 0x4f
    
    # Common x64 patterns
    X64_PATTERNS = [
        b'\x48\x89',  # mov with REX.W prefix (common in x64 prologue)
        b'\x48\x8b',  # mov with REX.W prefix
        b'\x48\x83',  # arithmetic with REX.W prefix
    ]
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def detect_from_pe(self, pe_path: str) -> Optional[str]:
        """
        Detect architecture from PE file headers.
        
        Returns:
            "x64", "x86", or None if detection fails
        """
        
        if not pe_path or not Path(pe_path).exists():
            self.logger.debug(f"PE file not found: {pe_path}")
            return None
        
        self.logger.info(f"Analyzing PE file for architecture: {pe_path}")
        
        try:
            pe = pefile.PE(pe_path, fast_load=True)
            machine = pe.FILE_HEADER.Machine
            pe.close()
            
            if machine == self.MACHINE_X64:
                self.logger.debug(f"PE Machine type: 0x{machine:x} (x64)")
                return "x64"
            elif machine == self.MACHINE_X86:
                self.logger.debug(f"PE Machine type: 0x{machine:x} (x86)")
                return "x86"
            else:
                self.logger.warning(f"Unknown PE Machine type: 0x{machine:x}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to read PE file: {e}")
            return None
    
    def detect_from_heuristics(self, binary_data: bytes, sample_size: int = 256) -> str:
        """
        Detect architecture using binary heuristics.
        
        Strategy:
        1. Check for REX prefixes (0x40-0x4f) in first sample_size bytes
        2. Look for common x64 instruction patterns
        3. Default to x86 if no x64 indicators found
        
        Returns:
            "x64" or "x86"
        """
        self.logger.info("Using heuristic architecture detection")
        
        sample = binary_data[:sample_size]
        
        # Count REX prefixes
        rex_count = sum(1 for b in sample if self.REX_PREFIX_START <= b <= self.REX_PREFIX_END)
        
        if rex_count > 5:  # Arbitrary threshold
            self.logger.debug(f"Found {rex_count} REX prefixes, likely x64")
            return "x64"
        
        # Check for x64 patterns
        for pattern in self.X64_PATTERNS:
            if pattern in sample:
                self.logger.debug(f"Found x64 pattern: {pattern.hex()}, likely x64")
                return "x64"
        
        self.logger.debug("No x64 indicators found, defaulting to x86")
        return "x86"
    
    def detect(self, binary_data: bytes, pe_file: Optional[str] = None) -> str:
        """
        Detect architecture using priority strategy.
        
        Priority:
        1. PE file header (if provided)
        2. Binary heuristics
        3. Default to x86
        
        Returns:
            "x64" or "x86"
        """
        # Strategy 1: PE file header
        if pe_file:
            arch = self.detect_from_pe(pe_file)
            if arch:
                self.logger.info(f"Architecture detected from PE: {arch}")
                return arch
        
        # Strategy 2: Heuristics
        arch = self.detect_from_heuristics(binary_data)
        self.logger.info(f"Architecture detected from heuristics: {arch}")
        return arch


class Disassembler:
    """Disassemble .text section binary files for EXE analysis."""
    
    def __init__(self, input_path: str, output_dir: str, params: Optional[Dict[str, Any]] = None):
        """
        Initialize EXE disassembler.
        
        Args:
            input_path: Path to .bin file (.text section)
            output_dir: Directory for JSON, text output
            params: Optional parameters:
                - verbose: bool - Enable debug logging
                - pe_file: str - Original PE for accurate arch detection
                - base_addr: str - Disassembly base (default: "0x1000")
                - output_filename: str - Custom JSON output filename
        """
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.params = params or {}
        
        # Extract parameters
        self.verbose = self.params.get("verbose", False)
        self.pe_file = self.params.get("pe_file")
        self.base_addr_str = self.params.get("base_addr", "0x1000")
        self.custom_filename = self.params.get("output_filename")
        
        # Parse base address
        try:
            self.base_addr = int(self.base_addr_str, 16) if self.base_addr_str.startswith("0x") else int(self.base_addr_str)
        except ValueError:
            self.base_addr = 0x1000
        
        # Setup logging
        self.logger = setup_logging(self.verbose)
        self.logger.name = "Disassembler"
        
        # Initialize components
        self.arch_detector = ArchitectureDetector(self.logger)
        self.binary_data = None
        self.architecture = None
        self.disassembler = None
        self.instructions = []
    
    def validate_input(self) -> bool:
        """Validate input .bin file exists and is readable."""
        self.logger.info(f"Validating input file: {self.input_path}")
        
        if not self.input_path.exists():
            self.logger.error(f"Input file does not exist: {self.input_path}")
            return False
        
        if not self.input_path.is_file():
            self.logger.error(f"Input path is not a file: {self.input_path}")
            return False
        
        size = self.input_path.stat().st_size
        if size == 0:
            self.logger.error(f"Input file is empty: {self.input_path}")
            return False
        
        self.logger.debug(f"Input file validated successfully (size: {size} bytes)")
        return True
    
    def ensure_output_directory(self) -> bool:
        """Create output directory if it doesn't exist."""
        self.logger.info(f"Ensuring output directory exists: {self.output_dir}")
        
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Output directory ready: {self.output_dir}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create output directory: {e}")
            return False
    
    def load_binary(self) -> bool:
        """Load binary data from .bin file."""
        self.logger.info("Loading binary data...")
        
        try:
            with open(self.input_path, 'rb') as f:
                self.binary_data = f.read()
            
            self.logger.debug(f"Loaded {len(self.binary_data)} bytes")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load binary file: {e}")
            return False
    
    def detect_architecture(self) -> bool:
        """Detect binary architecture."""
        self.logger.info("Detecting architecture...")
        
        try:
            self.architecture = self.arch_detector.detect(self.binary_data, self.pe_file)
            self.logger.info(f"Architecture: {self.architecture}")
            return True
        except Exception as e:
            self.logger.error(f"Architecture detection failed: {e}")
            return False
    
    def initialize_disassembler(self) -> bool:
        """Initialize Capstone disassembler with detected architecture."""
        self.logger.info("Initializing Capstone disassembler...")
        
        try:
            if self.architecture == "x64":
                mode = capstone.CS_MODE_64
                self.logger.debug("Using CS_MODE_64")
            else:
                mode = capstone.CS_MODE_32
                self.logger.debug("Using CS_MODE_32")
            
            self.disassembler = capstone.Cs(capstone.CS_ARCH_X86, mode)
            self.disassembler.detail = True  # Enable detailed instruction info
            
            self.logger.debug("Capstone initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Capstone: {e}")
            return False
    
    def disassemble_binary(self) -> bool:
        """Disassemble binary data using Capstone."""
        self.logger.info(f"Disassembling from base address: {self.base_addr_str}")
        
        try:
            instruction_count = 0
            error_count = 0
            current_offset = 0
            
            for instruction in self.disassembler.disasm(self.binary_data, self.base_addr):
                # Skip zero-size instructions
                if instruction.size == 0:
                    self.logger.debug(f"Skipping zero-size instruction at 0x{instruction.address:x}")
                    error_count += 1
                    continue
                
                # Extract instruction details
                instr_data = {
                    "address": f"0x{instruction.address:x}",
                    "mnemonic": instruction.mnemonic,
                    "operands": instruction.op_str,
                    "bytes": instruction.bytes.hex()
                }
                
                self.instructions.append(instr_data)
                instruction_count += 1
                current_offset = instruction.address - self.base_addr + instruction.size
                
                if self.verbose and instruction_count % 100 == 0:
                    self.logger.debug(f"Disassembled {instruction_count} instructions...")
            
            # Check if we disassembled everything
            bytes_remaining = len(self.binary_data) - current_offset
            if bytes_remaining > 0:
                self.logger.warning(f"{bytes_remaining} bytes could not be disassembled")
                error_count += bytes_remaining
            
            self.logger.info(f"Disassembly complete: {instruction_count} instructions")
            if error_count > 0:
                self.logger.warning(f"Encountered {error_count} errors/skipped bytes")
            
            return instruction_count > 0
        except Exception as e:
            self.logger.error(f"Disassembly failed: {e}")
            
            # Fallback: try alternate architecture mode
            if self.attempt_fallback_disassembly():
                return True
            
            return False
    
    def attempt_fallback_disassembly(self) -> bool:
        """Attempt disassembly with alternate architecture mode."""
        fallback_arch = "x86" if self.architecture == "x64" else "x64"
        self.logger.warning(f"Attempting fallback disassembly with {fallback_arch} mode...")
        
        try:
            # Switch architecture
            original_arch = self.architecture
            self.architecture = fallback_arch
            
            # Reinitialize disassembler
            if not self.initialize_disassembler():
                self.architecture = original_arch
                return False
            
            # Clear previous instructions
            self.instructions.clear()
            
            # Retry disassembly
            instruction_count = 0
            for instruction in self.disassembler.disasm(self.binary_data, self.base_addr):
                if instruction.size == 0:
                    continue
                
                instr_data = {
                    "address": f"0x{instruction.address:x}",
                    "mnemonic": instruction.mnemonic,
                    "operands": instruction.op_str,
                    "bytes": instruction.bytes.hex()
                }
                
                self.instructions.append(instr_data)
                instruction_count += 1
            
            if instruction_count > 0:
                self.logger.info(f"Fallback successful: {instruction_count} instructions using {fallback_arch}")
                return True
            else:
                self.logger.error("Fallback disassembly produced no results")
                self.architecture = original_arch
                return False
        except Exception as e:
            self.logger.error(f"Fallback disassembly failed: {e}")
            self.architecture = original_arch
            return False
    
    def save_json_output(self) -> Optional[str]:
        """Save disassembly to JSON file (JSONL format - one instruction per line)."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if self.custom_filename:
            filename = self.custom_filename if self.custom_filename.endswith('.json') else f"{self.custom_filename}.json"
        else:
            filename = f"disassembled_instructions.json"
        
        output_path = self.output_dir / filename
        self.logger.info(f"Saving JSON output: {output_path}")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.instructions, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"Saved {len(self.instructions)} instructions to JSON")
            return str(output_path)
        except Exception as e:
            self.logger.error(f"Failed to save JSON output: {e}")
            return None
    
    def save_text_output(self) -> Optional[str]:
        """Save human-readable text disassembly."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if self.custom_filename:
            base_name = self.custom_filename.replace('.json', '')
            filename = f"{base_name}.txt"
        else:
            filename = f"disassembled_instructions_{timestamp}.txt"
        
        output_path = self.output_dir / filename
        self.logger.info(f"Saving text output: {output_path}")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # Write header
                f.write("=" * 80 + "\n")
                f.write("EXE DISASSEMBLY OUTPUT\n")
                f.write("=" * 80 + "\n")
                f.write(f"Input File:   {self.input_path}\n")
                f.write(f"Architecture: {self.architecture}\n")
                f.write(f"Base Address: {self.base_addr_str}\n")
                f.write(f"Instructions: {len(self.instructions)}\n")
                f.write(f"Timestamp:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                
                # Write instructions
                for instr in self.instructions:
                    addr = instr['address']
                    mnemonic = instr['mnemonic']
                    operands = instr['operands']
                    bytes_hex = instr['bytes']
                    
                    # Format: address: mnemonic operands | bytes
                    line = f"{addr}: {mnemonic}"
                    if operands:
                        line += f" {operands}"
                    line += f" | {bytes_hex}"
                    
                    f.write(line + "\n")
            
            self.logger.debug(f"Saved {len(self.instructions)} instructions to text file")
            return str(output_path)
        except Exception as e:
            self.logger.error(f"Failed to save text output: {e}")
            return None
    
    def print_summary(self, json_path: str, text_path: str) -> None:
        """Print formatted console summary."""
        print("\n" + "=" * 80)
        print("EXE DISASSEMBLY SUMMARY")
        print("=" * 80)
        print(f"Input File:       {self.input_path}")
        print(f"Binary Size:      {len(self.binary_data)} bytes")
        print(f"Architecture:     {self.architecture}")
        print(f"Base Address:     {self.base_addr_str}")
        print(f"Instructions:     {len(self.instructions)}")
        
        if self.pe_file:
            print(f"PE Reference:     {self.pe_file}")
        
        print("\nOutput Files:")
        print(f"  JSON: {json_path}")
        print(f"  Text: {text_path}")
        
        # Show first few instructions as preview
        if self.instructions:
            print("\nFirst 5 Instructions:")
            for instr in self.instructions[:5]:
                addr = instr['address']
                mnemonic = instr['mnemonic']
                operands = instr['operands']
                line = f"  {addr}: {mnemonic}"
                if operands:
                    line += f" {operands}"
                print(line)
        
        print("=" * 80 + "\n")
    
    def disassemble(self) -> bool:
        """
        Execute full disassembly workflow.
        
        Returns:
            True if disassembly completed successfully, False otherwise
        """
        self.logger.info("Starting EXE disassembly workflow...")
        
        # Step 1: Validate input
        if not self.validate_input():
            return False
        
        # Step 2: Ensure output directory exists
        if not self.ensure_output_directory():
            return False
        
        # Step 3: Load binary data
        if not self.load_binary():
            return False
        
        # Step 4: Detect architecture
        if not self.detect_architecture():
            return False
        
        # Step 5: Initialize disassembler
        if not self.initialize_disassembler():
            return False
        
        # Step 6: Disassemble binary
        if not self.disassemble_binary():
            self.logger.error("Disassembly failed completely")
            return False
        
        # Step 7: Save outputs
        json_path = self.save_json_output()
        text_path = self.save_text_output()
        
        if not json_path or not text_path:
            self.logger.error("Failed to save output files")
            return False
        
        # Step 8: Print summary
        self.print_summary(json_path, text_path)
        
        self.logger.info("EXE disassembly completed successfully")
        return True


def run(input_path: str, output_dir: str, params: Optional[Dict[str, Any]] = None) -> bool:
    """
    Main entry point for rough.py compatibility.
    
    Args:
        input_path: Path to .bin file (.text section)
        output_dir: Directory for JSON, text output
        params: Optional parameters:
            - verbose: bool - Enable debug logging
            - pe_file: str - Original PE for accurate arch detection
            - base_addr: str - Disassembly base (default: "0x1000")
            - output_filename: str - Custom JSON output filename
    
    Returns:
        True if disassembly completed successfully, False otherwise
    """
    disassembler = Disassembler(input_path, output_dir, params)
    return disassembler.disassemble()


def main():
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="EXE Disassembler - Disassemble .text section binary files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i text_section.bin -o disasm_output
  %(prog)s -i text_section.bin -o output -v --pe EXE.exe
  %(prog)s -i text_section.bin -o output --base 0x140001000
  %(prog)s -i text_section.bin -o output --filename custom_output
        """
    )
    
    parser.add_argument( '-i', '--input',required=True,metavar='PATH', help='Path to .bin file (.text section)' )
    
    parser.add_argument('-o', '--output', required=True,metavar='DIR',help='Output directory for JSON and text files')
    
    parser.add_argument('-v', '--verbose', action='store_true',help='Enable verbose logging output')
    
    parser.add_argument('--pe',metavar='PATH', help='Original PE file for accurate architecture detection' )
    
    parser.add_argument('--base',metavar='ADDR',default='0x1000',help='Base address for disassembly (default: 0x1000)')
    
    parser.add_argument( '--filename', metavar='NAME',help='Custom output filename (without extension)' )
    
    args = parser.parse_args()
    
    # Build parameters dict
    params = {
        "verbose": args.verbose,
        "pe_file": args.pe,
        "base_addr": args.base,
        "output_filename": args.filename
    }
    
    # Execute disassembly
    success = run(args.input, args.output, params)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()