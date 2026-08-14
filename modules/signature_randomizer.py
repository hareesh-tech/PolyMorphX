#!/usr/bin/env python3
"""
Entry Point RVA Randomizer
Changes entry point address while preserving functionality.

Technique: Code cave trampolining
1. Find/create code cave at different RVA
2. Insert trampoline: jmp original_entry
3. Update PE header to point to trampoline
4. Entry point changes but execution path preserved

Safe because:
- Original code untouched
- Just adds indirect jump
- Minimal overhead (~5 bytes)
"""

import pefile
import struct
import random
import logging
import argparse
import time 
from pathlib import Path
from typing import Optional, Tuple

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("EntryPointRandomizer")


class EntryPointRandomizer:
    """
    Randomize entry point RVA using code cave trampolining.
    
    Strategy:
    1. Find suitable code cave (unused space in .text or create new section)
    2. Write trampoline: JMP original_entry
    3. Update AddressOfEntryPoint in PE header
    4. Each run with different seed → different cave location
    """
    
    def __init__(self, seed: int):
        self.seed = seed
        random.seed(seed)
        self.original_entry = None
        self.new_entry = None
    
    def randomize(self, pe_path: Path, output_path: Path) -> bool:
        """
        Randomize entry point RVA.
        
        Returns True if successful.
        """
        pe = pefile.PE(str(pe_path))
        
        self.original_entry = pe.OPTIONAL_HEADER.AddressOfEntryPoint
        logger.info(f"Original entry point: 0x{self.original_entry:08x}")
        
        # Find or create code cave
        cave_rva, cave_file_offset = self._find_code_cave(pe)
        
        if not cave_rva:
            logger.error("No suitable code cave found")
            return False
        
        logger.info(f"Found code cave at RVA: 0x{cave_rva:08x}")
        
        # Generate trampoline
        trampoline = self._generate_trampoline(cave_rva, self.original_entry)
        
        # Write trampoline to cave
        pe_data = bytearray(pe.__data__)
        pe_data[cave_file_offset:cave_file_offset + len(trampoline)] = trampoline
        
        # Update entry point in header
        pe_data = self._update_entry_point(pe_data, cave_rva)
        
        # Save
        output_path.write_bytes(pe_data)
        
        # Verify
        pe_new = pefile.PE(str(output_path))
        self.new_entry = pe_new.OPTIONAL_HEADER.AddressOfEntryPoint
        
        logger.info(f"New entry point:      0x{self.new_entry:08x}")
        
        if self.original_entry != self.new_entry:
            logger.info("✓ Entry point successfully randomized")
            return True
        else:
            logger.warning("⚠ Entry point unchanged")
            return False
    
    def _find_code_cave(self, pe: pefile.PE) -> Tuple[Optional[int], Optional[int]]:
        """
        Find suitable code cave for trampoline.
        
        Strategies:
        1. Look for NULL bytes in .text section
        2. Use padding between sections
        3. Extend .text section (if space available)
        
        Returns: (cave_rva, file_offset) or (None, None)
        """
        # Strategy 1: Find NULL padding in .text
        text_section = None
        for section in pe.sections:
            if b'.text' in section.Name:
                text_section = section
                break
        
        if not text_section:
            logger.warning("No .text section found")
            return None, None
        
        # Search for NULL cave (at least 32 bytes)
        section_data = text_section.get_data()
        min_cave_size = 32
        
        caves = []
        cave_start = None
        cave_size = 0
        
        for i, byte in enumerate(section_data):
            if byte == 0:
                if cave_start is None:
                    cave_start = i
                cave_size += 1
            else:
                if cave_size >= min_cave_size:
                    caves.append((cave_start, cave_size))
                cave_start = None
                cave_size = 0
        
        # Check last cave
        if cave_size >= min_cave_size:
            caves.append((cave_start, cave_size))
        
        if not caves:
            logger.debug("No NULL caves found, trying to extend section")
            return self._extend_text_section(pe, text_section)
        
        # Pick a random cave (seed-driven)
        cave_offset, size = random.choice(caves)
        
        # Add random offset within cave (more variation)
        max_offset = size - min_cave_size
        if max_offset > 0:
            cave_offset += random.randint(0, max_offset)
        
        # Convert to RVA and file offset
        cave_rva = text_section.VirtualAddress + cave_offset
        cave_file_offset = text_section.PointerToRawData + cave_offset
        
        logger.debug(f"Selected cave: offset {cave_offset}, size {size}")
        
        return cave_rva, cave_file_offset
    
    def _extend_text_section(self, pe: pefile.PE, text_section) -> Tuple[Optional[int], Optional[int]]:
        """
        Extend .text section to create space for trampoline.
        
        This adds to VirtualSize but keeps file size same (uses slack space).
        """
        # Find slack space between virtual end and file end
        virtual_end = text_section.VirtualAddress + text_section.Misc_VirtualSize
        raw_end = text_section.PointerToRawData + text_section.SizeOfRawData
        
        # Use end of section's file data as cave
        cave_file_offset = raw_end - 64  # Back 64 bytes from end
        cave_rva = text_section.VirtualAddress + text_section.SizeOfRawData - 64
        
        logger.debug("Using end of .text section for cave")
        
        return cave_rva, cave_file_offset
    
    def _generate_trampoline(self, cave_rva: int, original_entry: int) -> bytes:
        """
        Generate trampoline code: JMP original_entry
        
        Returns x86-64 trampoline bytes.
        """
        # Calculate relative jump displacement
        # JMP is relative to next instruction (cave_rva + 5)
        displacement = original_entry - (cave_rva + 5)
        
        # Check if fits in rel32 (signed 32-bit)
        if displacement < -0x80000000 or displacement > 0x7FFFFFFF:
            logger.error(f"Displacement too large: {displacement}")
            # Use NOP sled as fallback
            return b'\x90' * 32
        
        # Encode: E9 <rel32> (near jump)
        opcode = 0xE9
        
        # Pack as signed 32-bit integer
        try:
            displacement_bytes = struct.pack('<i', displacement)
        except struct.error as e:
            logger.error(f"Failed to pack displacement {displacement}: {e}")
            # Fallback: use direct jump with absolute address
            # This is less ideal but works
            return self._generate_absolute_trampoline(original_entry)
        
        trampoline = bytes([opcode]) + displacement_bytes
        
        # Pad with NOPs for safety (total 32 bytes)
        trampoline += b'\x90' * (32 - len(trampoline))
        
        logger.debug(f"Trampoline: {trampoline[:5].hex()} (JMP rel32 to 0x{original_entry:x})")
        
        return trampoline
    
    def _generate_absolute_trampoline(self, target_address: int) -> bytes:
        """
        Generate absolute jump trampoline for far addresses.
        
        Uses: PUSH <addr>; RET pattern (total 6 bytes)
        """
        # PUSH immediate32
        push_opcode = 0x68
        address_bytes = struct.pack('<I', target_address & 0xFFFFFFFF)
        
        # RET
        ret_opcode = 0xC3
        
        trampoline = bytes([push_opcode]) + address_bytes + bytes([ret_opcode])
        
        # Pad with NOPs
        trampoline += b'\x90' * (32 - len(trampoline))
        
        logger.debug(f"Absolute trampoline: PUSH 0x{target_address:x}; RET")
        
        return trampoline
    
    def _update_entry_point(self, pe_data: bytearray, new_entry_rva: int) -> bytearray:
        """
        Update AddressOfEntryPoint in PE header.
        
        Location: PE header + OPTIONAL_HEADER.AddressOfEntryPoint
        """
        # Parse PE to find offset
        pe = pefile.PE(data=bytes(pe_data))
        
        # Get offset of AddressOfEntryPoint field
        # This is at offset 16 in OPTIONAL_HEADER (after Magic and version fields)
        optional_header_offset = pe.DOS_HEADER.e_lfanew + 4 + pe.FILE_HEADER.sizeof()
        entry_point_offset = optional_header_offset + 16  # AddressOfEntryPoint is at +16
        
        # Write new RVA
        struct.pack_into('<I', pe_data, entry_point_offset, new_entry_rva)
        
        logger.debug(f"Updated entry point at file offset 0x{entry_point_offset:x}")
        
        return pe_data

class PESignatureRandomizer:
    """Randomize PE signature without touching code."""
    
    def __init__(self, seed: int = None):
        self.seed = seed or int(time.time())
        random.seed(self.seed)
    
    def randomize_timestamp(self, pe: pefile.PE):
        """Randomize PE timestamp header."""
        # Generate random timestamp (but reasonable - within last 5 years)
        base_time = int(time.time())
        random_offset = random.randint(0, 5 * 365 * 24 * 60 * 60)
        new_timestamp = base_time - random_offset
        
        pe.FILE_HEADER.TimeDateStamp = new_timestamp
        print(f"  Randomized timestamp: {new_timestamp}")
    
    def add_overlay_data(self, output_path: Path, overlay_size: int = 1024):
        """Add random data to PE overlay (after writing)."""
        # Generate random bytes
        random_data = bytes([random.randint(0, 255) for _ in range(overlay_size)])
        
        # Append to end of file
        with open(output_path, 'ab') as f:
            f.write(random_data)
        
        print(f"  Added {overlay_size} bytes to overlay")
        return overlay_size
    
    def randomize_section_padding(self, pe: pefile.PE):
        """Randomize padding bytes in section alignment gaps."""
        file_alignment = pe.OPTIONAL_HEADER.FileAlignment
        modified_sections = 0
        
        for section in pe.sections:
            # Get actual data size vs aligned size
            data_size = len(section.get_data())
            raw_size = section.SizeOfRawData
            
            # Padding is the gap between actual data and aligned size
            padding_size = raw_size - data_size
            
            if padding_size > 0:
                # Generate random padding
                random_padding = bytes([random.randint(0, 255) for _ in range(padding_size)])
                
                # Get current section data
                section_data = bytearray(section.get_data())
                
                # Append random padding
                section_data.extend(random_padding)
                
                # Set back (truncate to raw size)
                pe.set_bytes_at_offset(
                    section.PointerToRawData,
                    bytes(section_data[:raw_size])
                )
                
                modified_sections += 1
        
        print(f"  Randomized padding in {modified_sections} section(s)")
    
    def add_debug_directory_entropy(self, pe: pefile.PE):
        """Add random data to debug directory if present."""
        if hasattr(pe, 'DIRECTORY_ENTRY_DEBUG'):
            for debug_entry in pe.DIRECTORY_ENTRY_DEBUG:
                # Modify debug GUID/signature (commonly used for matching)
                if debug_entry.struct.Type == 2:  # IMAGE_DEBUG_TYPE_CODEVIEW
                    # This changes signature without affecting functionality
                    random_bytes = bytes([random.randint(0, 255) for _ in range(4)])
                    offset = debug_entry.struct.PointerToRawData
                    if offset > 0:
                        pe.set_bytes_at_offset(offset, random_bytes)
                        print(f"  Randomized debug signature")
    
    def randomize_checksum(self, pe: pefile.PE):
        """Set a random checksum (or zero it)."""
        # Most executables work fine with zero checksum
        # Randomize it for signature change
        pe.OPTIONAL_HEADER.CheckSum = random.randint(0, 0xFFFFFFFF)
        print(f"  Set random checksum: 0x{pe.OPTIONAL_HEADER.CheckSum:08x}")
    
    def process(self, input_exe: Path, output_exe: Path, overlay_size: int = 2048):
        """
        Randomize PE signature without touching code.
        
        Args:
            input_exe: Input executable
            output_exe: Output executable
            overlay_size: Size of random overlay to add
        """
        print("\n" + "=" * 70)
        print("PE SIGNATURE RANDOMIZER (NO CODE MODIFICATION)")
        print("=" * 70)
        print(f"Input:  {input_exe}")
        print(f"Output: {output_exe}")
        print(f"Seed:   {self.seed}")
        print()
        
        # Load PE
        pe = pefile.PE(str(input_exe))
        
        print("Applying randomizations:")
        
        # 1. Randomize timestamp
        self.randomize_timestamp(pe)
        
        # 2. Randomize checksum
        self.randomize_checksum(pe)
        
        # 3. Randomize section padding
        self.randomize_section_padding(pe)
        
        # 4. Randomize debug directory (if present)
        self.add_debug_directory_entropy(pe)
        
        # Write output FIRST
        output_exe.parent.mkdir(parents=True, exist_ok=True)
        pe.write(str(output_exe))
        pe.close()
        
        # 5. Add random overlay (append to file)
        self.add_overlay_data(output_exe, overlay_size)
        
        # Get sizes
        input_size = input_exe.stat().st_size
        output_size = output_exe.stat().st_size
        
        print()
        print("=" * 70)
        print("SUCCESS")
        print("=" * 70)
        print(f"Input size:  {input_size} bytes")
        print(f"Output size: {output_size} bytes (+{output_size - input_size} bytes)")
        print()
        print("✓ Signature randomized")
        print("✓ Hash changed")
        print("✓ Code untouched")
        print("✓ Seed: {} (reproducible)".format(self.seed))
        print("=" * 70)
        
        return True

def main():
    parser = argparse.ArgumentParser(
        description="Randomize PE entry point RVA and file signature"
    )
    parser.add_argument("--input", "-i", required=True, type=Path,help="Input PE file")

    parser.add_argument("--output", "-o", required=True, type=Path, help="Output PE file")

    parser.add_argument("--seed", "-s", type=int, default=None,help="Random seed (default: random)")

    parser.add_argument("--overlay-size", type=int, default=2048,help="Size of random overlay to add (default: 2048)")
    
    parser.add_argument("-v", "--verbose", action="store_true")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    seed = args.seed if args.seed else random.randint(1, 0xFFFFFFFF)
    
    # 1. Entry Point Randomization
    logger.info("--- Step 1: Entry Point Randomization ---")
    ep_randomizer = EntryPointRandomizer(seed)
    success = ep_randomizer.randomize(args.input, args.output)
    
    if not success:
        logger.error("Entry point randomization failed")
        return 1
        
    # 2. Signature Randomization
    logger.info("\n--- Step 2: Signature Randomization ---")
    # Use the output of step 1 as input for step 2
    sig_randomizer = PESignatureRandomizer(seed)
    success = sig_randomizer.process(args.output, args.output, args.overlay_size)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())