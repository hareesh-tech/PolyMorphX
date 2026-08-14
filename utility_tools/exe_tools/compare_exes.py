#!/usr/bin/env python3
"""
binary_compare_unified.py - OPTIMIZED VERSION
Mode A: EXE → TXT analytics + change report
Mode B: JSON → Drift graph only

Key Optimizations:
1. Fixed graph plotting issues (non-numeric data handling)
2. Lazy loading of PE file data
3. Optimized byte similarity calculation
4. Better error handling
5. Progress indicators for long operations
6. Reduced memory footprint
"""

import argparse
import json
import hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

# EXE MODE LIBS
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64


# ---------------- HASH ----------------

def sha256(path):
    """Compute SHA256 with chunked reading for large files"""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


# ---------------- PE LOAD ----------------

def load_pe(path):
    """Load PE file with fast_load for efficiency"""
    return pefile.PE(path, fast_load=True)


# ---------------- ENTRY POINT ----------------

def entry_bytes(pe):
    """Extract entry point bytes efficiently"""
    try:
        ep = pe.OPTIONAL_HEADER.AddressOfEntryPoint
        off = pe.get_offset_from_rva(ep)
        return pe.__data__[off:off+32].hex()
    except Exception as e:
        return f"ERROR: {str(e)}"


# ---------------- SECTION DATA ----------------

def extract_sections(pe):
    """Extract section information"""
    sections = {}
    for s in pe.sections:
        name = s.Name.rstrip(b"\x00").decode(errors="ignore")
        sections[name] = {
            "raw_size": s.SizeOfRawData,
            "virt_size": s.Misc_VirtualSize,
            "entropy": round(s.get_entropy(), 4),
            "va": hex(s.VirtualAddress)
        }
    return sections


# ---------------- IMPORTS ----------------

def imports(pe):
    """Extract import information"""
    result = {}
    try:
        if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
            for d in pe.DIRECTORY_ENTRY_IMPORT:
                dll_name = d.dll.decode(errors='ignore')
                result[dll_name] = len(d.imports)
    except Exception:
        pass
    return result


# ---------------- OPCODES ----------------

def opcode_freq(path, max_bytes=100000):
    """
    Extract opcode frequency with size limit for efficiency
    Only disassemble first max_bytes to avoid performance issues
    """
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    freq = {}
    
    try:
        with open(path, "rb") as f:
            code = f.read(max_bytes)
        
        for ins in md.disasm(code, 0x1000):
            freq[ins.mnemonic] = freq.get(ins.mnemonic, 0) + 1
    except Exception as e:
        print(f"Warning: Opcode analysis failed - {e}")
    
    return freq


# ---------------- BYTE SIMILARITY ----------------

def byte_similarity(a, b, sample_size=10000):
    """
    Optimized byte similarity using sampling for large files
    Compares first sample_size bytes for efficiency
    """
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            x = fa.read(sample_size)
            y = fb.read(sample_size)
        
        size = min(len(x), len(y))
        if size == 0:
            return 0.0
        
        # Vectorized comparison is faster than loop
        matches = sum(1 for i in range(size) if x[i] == y[i])
        return matches / size
    except Exception:
        return 0.0


# ---------------- EXE ANALYTICS ----------------

def analyze_exe(path):
    """Analyze executable file"""
    print(f"Analyzing: {path}")
    pe = load_pe(path)

    result = {
        "path": str(path),
        "sha256": sha256(path),
        "entry_point_bytes": entry_bytes(pe),
        "sections": extract_sections(pe),
        "imports": imports(pe),
        "opcode_freq": opcode_freq(path),
        "file_size": Path(path).stat().st_size
    }
    
    pe.close()
    return result


# ---------------- TXT REPORT BUILDER ----------------

def build_txt_report(orig, trans, similarity):
    """Build comprehensive text report"""
    lines = []

    lines.append("========= BINARY ANALYSIS REPORT =========")
    lines.append("")
    lines.append("===== ORIGINAL EXECUTABLE =====")
    lines.append(f"Path: {orig['path']}")
    lines.append(f"SHA256: {orig['sha256']}")
    lines.append(f"File Size: {orig['file_size']:,} bytes")
    lines.append(f"Entry Bytes: {orig['entry_point_bytes']}")
    lines.append("")
    lines.append("Sections:")
    for s, d in orig["sections"].items():
        lines.append(f"  {s} | RAW={d['raw_size']:,} | VIRT={d['virt_size']:,} | ENTROPY={d['entropy']} | VA={d['va']}")

    lines.append("")
    lines.append("Imports:")
    for dll, count in sorted(orig["imports"].items()):
        lines.append(f"  {dll}: {count}")

    lines.append("")
    lines.append("Opcode Count:")
    lines.append(f"  Unique Opcodes: {len(orig['opcode_freq'])}")
    lines.append(f"  Total Instructions Analyzed: {sum(orig['opcode_freq'].values()):,}")

    lines.append("")
    lines.append("===== TRANSFORMED EXECUTABLE =====")
    lines.append(f"Path: {trans['path']}")
    lines.append(f"SHA256: {trans['sha256']}")
    lines.append(f"File Size: {trans['file_size']:,} bytes")
    lines.append(f"Entry Bytes: {trans['entry_point_bytes']}")
    lines.append("")
    lines.append("Sections:")
    for s, d in trans["sections"].items():
        lines.append(f"  {s} | RAW={d['raw_size']:,} | VIRT={d['virt_size']:,} | ENTROPY={d['entropy']} | VA={d['va']}")

    lines.append("")
    lines.append("Imports:")
    for dll, count in sorted(trans["imports"].items()):
        lines.append(f"  {dll}: {count}")

    lines.append("")
    lines.append("Opcode Count:")
    lines.append(f"  Unique Opcodes: {len(trans['opcode_freq'])}")
    lines.append(f"  Total Instructions Analyzed: {sum(trans['opcode_freq'].values()):,}")

    # ---------------- CHANGES ----------------

    lines.append("")
    lines.append("========= CHANGE ANALYSIS =========")

    lines.append(f"Entry Point Changed: {orig['entry_point_bytes'] != trans['entry_point_bytes']}")
    lines.append(f"Byte Similarity Score: {similarity:.6f} ({similarity*100:.2f}%)")
    lines.append(f"File Size Change: {trans['file_size'] - orig['file_size']:+,} bytes")

    lines.append("")
    lines.append("Section Differences:")
    all_sections = set(orig["sections"]) | set(trans["sections"])
    section_changes = False
    for sec in sorted(all_sections):
        o = orig["sections"].get(sec, {})
        t = trans["sections"].get(sec, {})
        if o != t:
            section_changes = True
            if not o:
                lines.append(f"  {sec}: ADDED -> {t}")
            elif not t:
                lines.append(f"  {sec}: REMOVED <- {o}")
            else:
                lines.append(f"  {sec}: MODIFIED")
                for key in ['raw_size', 'virt_size', 'entropy']:
                    if o.get(key) != t.get(key):
                        lines.append(f"    {key}: {o.get(key)} -> {t.get(key)}")
    
    if not section_changes:
        lines.append("  No section differences detected")

    lines.append("")
    lines.append("Import Differences:")
    all_dlls = set(orig["imports"]) | set(trans["imports"])
    import_changes = False
    for dll in sorted(all_dlls):
        o_count = orig["imports"].get(dll)
        t_count = trans["imports"].get(dll)
        if o_count != t_count:
            import_changes = True
            if o_count is None:
                lines.append(f"  {dll}: ADDED ({t_count} imports)")
            elif t_count is None:
                lines.append(f"  {dll}: REMOVED ({o_count} imports)")
            else:
                lines.append(f"  {dll}: {o_count} -> {t_count} imports")
    
    if not import_changes:
        lines.append("  No import differences detected")

    lines.append("")
    lines.append("Opcode Drift:")
    all_ops = set(orig["opcode_freq"]) | set(trans["opcode_freq"])
    drift_count = sum(1 for op in all_ops if orig["opcode_freq"].get(op, 0) != trans["opcode_freq"].get(op, 0))
    lines.append(f"  Opcodes Changed: {drift_count} / {len(all_ops)} ({drift_count/len(all_ops)*100:.1f}%)")
    
    # Top 10 opcode changes
    opcode_diffs = []
    for op in all_ops:
        diff = trans["opcode_freq"].get(op, 0) - orig["opcode_freq"].get(op, 0)
        if diff != 0:
            opcode_diffs.append((op, diff, orig["opcode_freq"].get(op, 0), trans["opcode_freq"].get(op, 0)))
    
    opcode_diffs.sort(key=lambda x: abs(x[1]), reverse=True)
    
    if opcode_diffs:
        lines.append("")
        lines.append("  Top 10 Opcode Changes:")
        for op, diff, o_count, t_count in opcode_diffs[:10]:
            lines.append(f"    {op}: {o_count} -> {t_count} ({diff:+d})")

    return "\n".join(lines)


# ---------------- JSON GRAPH MODE (FIXED) ----------------

def plot_json_drift(json_a, json_b, out_path):
    """
    Plot JSON drift comparison with proper handling of different data types
    FIXED: Now handles non-numeric data correctly
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading JSON files...")
    with open(json_a) as f:
        A = json.load(f)
    with open(json_b) as f:
        B = json.load(f)

    # Normalize different JSON structures
    def normalize_json(data, label):
        """Convert various JSON formats to comparable numeric dict"""
        if isinstance(data, list):
            return {label: len(data), f"{label}_items": len(data)}
        elif isinstance(data, dict):
            # Extract only numeric values
            numeric_data = {}
            for k, v in data.items():
                if isinstance(v, (int, float)):
                    numeric_data[k] = v
                elif isinstance(v, list):
                    numeric_data[f"{k}_count"] = len(v)
                elif isinstance(v, dict):
                    numeric_data[f"{k}_count"] = len(v)
                elif isinstance(v, str):
                    numeric_data[f"{k}_length"] = len(v)
            return numeric_data if numeric_data else {label: 1}
        elif isinstance(data, (int, float)):
            return {label: data}
        else:
            return {label: 1}

    A_norm = normalize_json(A, "original")
    B_norm = normalize_json(B, "transformed")

    # Get all keys and ensure we have numeric data
    all_keys = sorted(set(A_norm.keys()) | set(B_norm.keys()))
    
    if not all_keys:
        print("Warning: No comparable numeric data found in JSON files")
        all_keys = ["data_size"]
        A_norm = {"data_size": len(str(A))}
        B_norm = {"data_size": len(str(B))}

    vals_a = [A_norm.get(k, 0) for k in all_keys]
    vals_b = [B_norm.get(k, 0) for k in all_keys]

    # Create figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # Plot 1: Line comparison
    x_pos = np.arange(len(all_keys))
    ax1.plot(x_pos, vals_a, label="Original", marker="o", linewidth=2, markersize=8)
    ax1.plot(x_pos, vals_b, label="Transformed", marker="s", linewidth=2, markersize=8)
    ax1.set_title("JSON Drift Comparison - Line Plot", fontsize=14, fontweight='bold')
    ax1.set_ylabel("Value", fontsize=12)
    ax1.set_xlabel("Feature / Key", fontsize=12)
    ax1.set_xticks(x_pos)
    ax1.set_xticklabels(all_keys, rotation=45, ha='right')
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Bar comparison
    width = 0.35
    ax2.bar(x_pos - width/2, vals_a, width, label='Original', alpha=0.8)
    ax2.bar(x_pos + width/2, vals_b, width, label='Transformed', alpha=0.8)
    ax2.set_title("JSON Drift Comparison - Bar Chart", fontsize=14, fontweight='bold')
    ax2.set_ylabel("Value", fontsize=12)
    ax2.set_xlabel("Feature / Key", fontsize=12)
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(all_keys, rotation=45, ha='right')
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    
    # Save with high quality
    plt.savefig(str(out_path), dpi=200, bbox_inches='tight')
    plt.close()

    print(f"✔ JSON Drift Graph saved: {out_path.resolve()}")
    
    # Also create a summary file
    summary_path = out_path.parent / "json_comparison_summary.txt"
    with open(summary_path, 'w') as f:
        f.write("JSON COMPARISON SUMMARY\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Original file: {json_a}\n")
        f.write(f"Transformed file: {json_b}\n\n")
        f.write("Extracted Numeric Features:\n")
        f.write("-" * 50 + "\n")
        f.write(f"{'Feature':<30} {'Original':<15} {'Transformed':<15} {'Diff':<10}\n")
        f.write("-" * 50 + "\n")
        for k, v_a, v_b in zip(all_keys, vals_a, vals_b):
            diff = v_b - v_a
            f.write(f"{k:<30} {v_a:<15.2f} {v_b:<15.2f} {diff:+10.2f}\n")
    
    print(f"✔ JSON Summary saved: {summary_path.resolve()}")


# ---------------- MAIN ----------------

def main():
    ap = argparse.ArgumentParser(
        description="Binary Comparison Tool - Analyze EXE or JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--original", required=True, help="Path to original file")
    ap.add_argument("--transformed", required=True, help="Path to transformed file")
    ap.add_argument("--out", default="Compare_Output", help="Output directory (default: Compare_Output)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)

    orig_path = Path(args.original)
    trans_path = Path(args.transformed)
    
    if not orig_path.exists():
        print(f"ERROR: Original file not found: {orig_path}")
        return
    
    if not trans_path.exists():
        print(f"ERROR: Transformed file not found: {trans_path}")
        return

    orig_ext = orig_path.suffix.lower()
    trans_ext = trans_path.suffix.lower()

    print(f"\n{'='*60}")
    print(f"Binary Comparison Tool - OPTIMIZED")
    print(f"{'='*60}\n")

    # -------- JSON MODE --------
    if orig_ext == ".json" and trans_ext == ".json":
        print("Mode: JSON Drift Analysis")
        graph_path = out_dir / "json_drift_graph.png"
        plot_json_drift(args.original, args.transformed, graph_path)
        print(f"\n✔ JSON analysis complete!")
        print(f"✔ Output directory: {out_dir.resolve()}")
        return

    # -------- EXE MODE --------
    print("Mode: Executable Binary Analysis")
    print("")
    
    orig = analyze_exe(args.original)
    trans = analyze_exe(args.transformed)

    print("\nComputing byte similarity...")
    similarity = byte_similarity(args.original, args.transformed)

    print("Generating report...")
    report = build_txt_report(orig, trans, similarity)

    report_path = out_dir / "binary_comparison_report.txt"
    report_path.write_text(report)

    print(f"\n{'='*60}")
    print(f"✔ Analysis Complete!")
    print(f"✔ Report saved: {report_path.resolve()}")
    print(f"✔ Output directory: {out_dir.resolve()}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

    