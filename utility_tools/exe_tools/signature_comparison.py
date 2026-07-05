#!/usr/bin/env python3
"""
Signature Comparison Tool
Shows what changes between original and randomized PE files.
"""

import hashlib
import pefile
from pathlib import Path
import argparse
import sys

def get_file_hash(filepath: Path) -> str:
    """Get SHA256 hash of entire file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        sha256.update(f.read())
    return sha256.hexdigest()

def get_section_hash(pe: pefile.PE, section_name: str) -> str:
    """Get hash of a specific section."""
    for section in pe.sections:
        if section_name.encode() in section.Name:
            sha256 = hashlib.sha256()
            sha256.update(section.get_data())
            return sha256.hexdigest()
    return "N/A"

def get_imphash(pe: pefile.PE) -> str:
    """Get import hash."""
    try:
        return pe.get_imphash()
    except:
        return "N/A"

def compare_signatures(original: Path, randomized: Path, file=sys.stdout):
    """Compare signature characteristics."""
    def write(s):
        print(s, file=file)

    write("\n" + "=" * 70)
    write("SIGNATURE COMPARISON")
    write("=" * 70)
    write(f"Original:   {original}")
    write(f"Randomized: {randomized}")
    write("")
    
    # Load PEs
    pe_orig = pefile.PE(str(original))
    pe_rand = pefile.PE(str(randomized))
    
    # File hashes
    write("=" * 70)
    write("FILE-LEVEL SIGNATURES (What changes)")
    write("=" * 70)
    
    hash_orig = get_file_hash(original)
    hash_rand = get_file_hash(randomized)
    match = "✓ DIFFERENT" if hash_orig != hash_rand else "✗ SAME"
    write(f"\n1. File Hash (SHA256):")
    write(f"   Original:   {hash_orig[:32]}...")
    write(f"   Randomized: {hash_rand[:32]}...")
    write(f"   Status: {match}")
    
    # File size
    size_orig = original.stat().st_size
    size_rand = randomized.stat().st_size
    match = "✓ DIFFERENT" if size_orig != size_rand else "✗ SAME"
    write(f"\n2. File Size:")
    write(f"   Original:   {size_orig:,} bytes")
    write(f"   Randomized: {size_rand:,} bytes")
    write(f"   Status: {match}")
    
    # PE Timestamp
    ts_orig = pe_orig.FILE_HEADER.TimeDateStamp
    ts_rand = pe_rand.FILE_HEADER.TimeDateStamp
    match = "✓ DIFFERENT" if ts_orig != ts_rand else "✗ SAME"
    write(f"\n3. PE Timestamp:")
    write(f"   Original:   {ts_orig}")
    write(f"   Randomized: {ts_rand}")
    write(f"   Status: {match}")
    
    # PE Checksum
    cs_orig = pe_orig.OPTIONAL_HEADER.CheckSum
    cs_rand = pe_rand.OPTIONAL_HEADER.CheckSum
    match = "✓ DIFFERENT" if cs_orig != cs_rand else "✗ SAME"
    write(f"\n4. PE Checksum:")
    write(f"   Original:   0x{cs_orig:08x}")
    write(f"   Randomized: 0x{cs_rand:08x}")
    write(f"   Status: {match}")
    
    # Code section
    write("\n" + "=" * 70)
    write("CODE-LEVEL SIGNATURES")
    write("=" * 70)
    
    text_hash_orig = get_section_hash(pe_orig, '.text')
    text_hash_rand = get_section_hash(pe_rand, '.text')
    match = "✓ DIFFERENT" if text_hash_orig != text_hash_rand else "✗ SAME"
    write(f"\n5. .text Section Hash:")
    write(f"   Original:   {text_hash_orig[:32]}...")
    write(f"   Randomized: {text_hash_rand[:32]}...")
    write(f"   Status: {match}")
    
    # Import hash
    imphash_orig = get_imphash(pe_orig)
    imphash_rand = get_imphash(pe_rand)
    match = "✓ DIFFERENT" if imphash_orig != imphash_rand else "✗ SAME"
    write(f"\n6. Import Hash (imphash):")
    write(f"   Original:   {imphash_orig}")
    write(f"   Randomized: {imphash_rand}")
    write(f"   Status: {match}")
    
    # Entry point
    ep_orig = pe_orig.OPTIONAL_HEADER.AddressOfEntryPoint
    ep_rand = pe_rand.OPTIONAL_HEADER.AddressOfEntryPoint
    match = "✓ DIFFERENT" if ep_orig != ep_rand else "✗ SAME"
    write(f"\n7. Entry Point RVA:")
    write(f"   Original:   0x{ep_orig:08x}")
    write(f"   Randomized: 0x{ep_rand:08x}")
    write(f"   Status: {match}")
    
    # # Summary
    # print("\n" + "=" * 70)
    # print("DETECTION BYPASS SUMMARY")
    # print("=" * 70)
    # print(f"")
    # print("=" * 70)
    
    pe_orig.close()
    pe_rand.close()

def main():
    parser = argparse.ArgumentParser(description="Compare PE signatures")
    parser.add_argument('--original', required=True, help='Original executable')
    parser.add_argument('--random', required=True, help='Randomized executable')
    parser.add_argument('--output', required=True, type=Path,
                        help='Output report file path')
    
    args = parser.parse_args()

    original = Path(args.original)
    randomized = Path(args.random)
    output_file = Path(args.output)

    if not original.exists():
        print(f"ERROR: Original file not found: {original}")
        return 1

    if not randomized.exists():
        print(f"ERROR: Randomized file not found: {randomized}")
        return 1

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        compare_signatures(original, randomized, file=f)

    print(f"\nSignature comparison report saved to: {output_file}")
    return 0

if __name__ == "__main__":
    sys.exit(main())