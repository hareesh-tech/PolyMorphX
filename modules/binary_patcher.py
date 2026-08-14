#!/usr/bin/env python3
"""
Binary Patcher Module
Applies byte-level patches from transformation results to executable files.
Supports PE (Windows) and ELF (Linux) formats.
"""
import json
import struct
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Optional
try:
    import pefile
    PE_SUPPORT = True
except ImportError:
    PE_SUPPORT = False
    logging.warning("pefile not installed, PE support disabled")

from datetime import datetime

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BinaryPatcher")

class Patcher:
    def __init__(self, exe_path: Path):
        self.exe_path = exe_path
        self.binary = bytearray(exe_path.read_bytes())
        
# In binary_patcher.py, add to apply_patches() method:

    def apply_patches(self, transformations: List[Dict]) -> bool:
        success = True
        
        # NEW: Sort by address ascending to catch overlaps
        sorted_transforms = sorted(
            [t for t in transformations if t.get("applied")],
            key=lambda t: t["address"]
        )
        
        # NEW: Check for overlapping patches
        for i in range(len(sorted_transforms) - 1):
            t1 = sorted_transforms[i]
            t2 = sorted_transforms[i + 1]
            addr1 = t1["address"]
            addr2 = t2["address"]
            size1 = len(bytes.fromhex(t1["new_bytes"]))
            
            if addr1 + size1 > addr2:
                logger.error(
                    f"OVERLAPPING PATCHES: 0x{addr1:x}+{size1} overlaps 0x{addr2:x}"
                )
                success = False
        
        total_patches = len(sorted_transforms)
        if total_patches == 0:
            logger.info("No patches to apply.")
            return True

        logger.info(f"Starting application of {total_patches} patches...")
        applied_count = 0
        last_percentage = 0

        # Apply patches
        for t in sorted_transforms:
            addr = t["address"]
            new_bytes = bytes.fromhex(t["new_bytes"])
            original_bytes = bytes.fromhex(t["original_bytes"])

            # Find file offset for this virtual address
            offset = self._rva_to_offset(addr)
            if offset is None:
                logger.error(f"Cannot map address 0x{addr:x} to file offset")
                success = False
                continue
            
            # Verify original bytes match (safety check)
            current = self.binary[offset:offset+len(original_bytes)]
            if current != original_bytes:
                logger.warning(
                    f"Byte mismatch at 0x{addr:x}: "
                    f"expected {original_bytes.hex()}, found {current.hex()}"
                )
                continue
            
            # Apply patch
            self.binary[offset:offset+len(new_bytes)] = new_bytes
            logger.debug(f"Patched 0x{addr:x} (offset 0x{offset:x}): {original_bytes.hex()} -> {new_bytes.hex()}")
            
            applied_count += 1
            percentage = int((applied_count / total_patches) * 100)
            
            if percentage >= last_percentage + 5:
                logger.info(f"Progress: {percentage}% ({applied_count}/{total_patches} patches applied)")
                last_percentage = percentage

        logger.info(f"Completed. {applied_count}/{total_patches} patches applied successfully.")
        return success
    
    
    def _rva_to_offset(self, rva: int) -> Optional[int]:
        """Convert RVA to file offset. Implementation depends on file format."""
        # Simplified implementation - assumes flat mapping or use pefile
        if PE_SUPPORT and self.exe_path.suffix.lower() in {'.exe', '.dll'}:
            logger.debug("Using PE format mapping")
            return self._pe_rva_to_offset(rva)
        
        else:
            # Assume raw binary or section at offset 0
            return rva
    
    def _pe_rva_to_offset(self, rva: int) -> Optional[int]:
        """Convert PE RVA to file offset using pefile."""
        pe = pefile.PE(data=self.binary)
        for section in pe.sections:
            if section.VirtualAddress <= rva < section.VirtualAddress + section.Misc_VirtualSize:
                logger.debug(f"Mapping RVA 0x{rva:x} to offset using PE section")
                return section.PointerToRawData + (rva - section.VirtualAddress)
        return None
    
    def save(self, output_path: Path):
        """Save patched binary."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.binary)
        logger.info(f"Patched binary saved: {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Apply transformation patches to binary executable"
    )
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--transforms", required=True, type=Path, help="transformed_instructions.json from engine")
    parser.add_argument("--output", required=True, type=Path, help="Output path for patched binary with filename 'polymorphed.exe')")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    with open(args.transforms) as f:
        data = json.load(f)
    
    patcher = Patcher(args.exe)
    if patcher.apply_patches(data["transformations"]):
        patcher.save(args.output)
        logger.info(f"Success: Patched binary saved to {args.output}")
    else:
        logger.warning("Some patches failed to apply")

if __name__ == "__main__":
    main()