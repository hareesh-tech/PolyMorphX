#!/usr/bin/env python3
"""
PE Analyzer - Production-grade PE file analysis and .text section extraction.
"""

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import pefile
except ImportError:
    print("ERROR: pefile library not found. Install with: pip install pefile")
    sys.exit(1)


# Configure logging
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure console-based logging with optional verbose mode."""
    logger = logging.getLogger("PEAnalyzer")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Console handler with formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    formatter = logging.Formatter(
        fmt='[%(asctime)s] %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


class PEAnalyzer:
    """PE file analyzer with section extraction and JSON output generation."""
    
    ARCHITECTURE_MAP = {
        0x10b: "x86",
        0x20b: "x64",
    }
    
    def __init__(self, input_path: str, output_dir: str, verbose: bool = False):
        """
        Initialize PE analyzer.
        
        Args:
            input_path: Path to PE executable file
            output_dir: Directory to save output files
            verbose: Enable verbose logging
        """
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.verbose = verbose
        self.logger = setup_logging(verbose)
        self.pe = None
        self.analysis_data = {}
        
    def validate_input(self) -> bool:
        """Validate input PE file exists and is accessible."""
        self.logger.info(f"Validating input file: {self.input_path}")
        
        if not self.input_path.exists():
            self.logger.error(f"Input file does not exist: {self.input_path}")
            return False
        
        if not self.input_path.is_file():
            self.logger.error(f"Input path is not a file: {self.input_path}")
            return False
        
        if self.input_path.stat().st_size == 0:
            self.logger.error(f"Input file is empty: {self.input_path}")
            return False
        
        self.logger.debug(f"Input file validated successfully (size: {self.input_path.stat().st_size} bytes)")
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
    
    def load_pe_file(self) -> bool:
        """Load and parse PE file."""
        self.logger.info("Loading PE file...")
        
        try:
            self.pe = pefile.PE(str(self.input_path), fast_load=False)
            self.logger.debug("PE file loaded successfully")
            return True
        except pefile.PEFormatError as e:
            self.logger.error(f"Invalid PE file format: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load PE file: {e}")
            return False
    
    def get_architecture(self) -> str:
        """Determine PE architecture (x86/x64)."""
        magic = self.pe.OPTIONAL_HEADER.Magic
        arch = self.ARCHITECTURE_MAP.get(magic, f"Unknown (0x{magic:x})")
        self.logger.debug(f"Architecture detected: {arch}")
        return arch
    
    def extract_pe_headers(self) -> Dict[str, Any]:
        """Extract PE header information."""
        self.logger.info("Extracting PE header information...")
        
        entry_point = self.pe.OPTIONAL_HEADER.AddressOfEntryPoint
        image_base = self.pe.OPTIONAL_HEADER.ImageBase
        sections_count = self.pe.FILE_HEADER.NumberOfSections
        
        headers = {
            "entry_point": f"0x{entry_point:x}",
            "image_base": f"0x{image_base:x}",
            "sections_count": sections_count
        }
        
        self.logger.debug(f"Entry Point: {headers['entry_point']}")
        self.logger.debug(f"Image Base: {headers['image_base']}")
        self.logger.debug(f"Section Count: {sections_count}")
        
        return headers
    
    def enumerate_sections(self) -> List[Dict[str, Any]]:
        """Enumerate all PE sections with detailed information."""
        self.logger.info("Enumerating PE sections...")
        
        sections = []
        for idx, section in enumerate(self.pe.sections, start=1):
            section_name = section.Name.decode('utf-8', errors='ignore').rstrip('\x00')
            
            section_data = {
                "name": section_name,
                "virtual_address": section.VirtualAddress,
                "virtual_size": section.Misc_VirtualSize,
                "raw_size": section.SizeOfRawData,
                "index": idx
            }
            
            sections.append(section_data)
            
            self.logger.debug(
                f"Section {idx}: {section_name:12s} | "
                f"VA: 0x{section.VirtualAddress:08x} | "
                f"VSize: {section.Misc_VirtualSize:8d} | "
                f"RawSize: {section.SizeOfRawData:8d}"
            )
        
        self.logger.info(f"Found {len(sections)} sections")
        return sections
    
    def find_text_section(self, sections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Locate .text section in PE file."""
        self.logger.info("Searching for .text section...")
        
        for section in sections:
            if section["name"].lower() == ".text":
                self.logger.debug(f"Found .text section at index {section['index']}")
                return section
        
        self.logger.warning(".text section not found in PE file")
        return None
    
    def extract_text_section(self, text_section_info: Dict[str, Any]) -> Optional[bytes]:
        """Extract raw bytes from .text section."""
        self.logger.info("Extracting .text section bytes...")
        
        try:
            # Find the actual section object
            for section in self.pe.sections:
                section_name = section.Name.decode('utf-8', errors='ignore').rstrip('\x00')
                if section_name.lower() == ".text":
                    data = section.get_data()
                    self.logger.debug(f"Extracted {len(data)} bytes from .text section")
                    return data
            
            self.logger.error("Failed to extract .text section data")
            return None
        except Exception as e:
            self.logger.error(f"Error extracting .text section: {e}")
            return None
    
    def save_text_section(self, data: bytes) -> Optional[str]:
        """Save .text section to binary file."""
        output_path = self.output_dir / "text_section.bin"
        self.logger.info(f"Saving .text section to: {output_path}")
        
        try:
            with open(output_path, 'wb') as f:
                f.write(data)
            self.logger.debug(f"Wrote {len(data)} bytes to {output_path}")
            return str(output_path)
        except Exception as e:
            self.logger.error(f"Failed to save .text section: {e}")
            return None
    
    def copy_original_pe(self) -> Optional[str]:
        """Copy original PE file to output directory."""
        output_path = self.output_dir / "parsed_executable.exe"
        self.logger.info(f"Copying original PE to: {output_path}")
        
        try:
            shutil.copy2(self.input_path, output_path)
            self.logger.debug(f"Copied {self.input_path} to {output_path}")
            return str(output_path)
        except Exception as e:
            self.logger.error(f"Failed to copy original PE: {e}")
            return None
    
    def save_json_output(self, data: Dict[str, Any]) -> Optional[str]:
        """Save analysis data to JSON file."""
        output_path = self.output_dir / "pe_analysis.json"
        self.logger.info(f"Saving JSON analysis to: {output_path}")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.debug(f"JSON analysis saved to {output_path}")
            return str(output_path)
        except Exception as e:
            self.logger.error(f"Failed to save JSON output: {e}")
            return None
    
    def print_summary(self, data: Dict[str, Any]) -> None:
        """Print formatted console summary of analysis."""
        print("\n" + "=" * 80)
        print("PE ANALYSIS SUMMARY")
        print("=" * 80)
        print(f"Input File:      {data['input_file']}")
        print(f"Architecture:    {data['architecture']}")
        print(f"Entry Point:     {data['pe_headers']['entry_point']}")
        print(f"Image Base:      {data['pe_headers']['image_base']}")
        print(f"Sections Count:  {data['pe_headers']['sections_count']}")
        
        if data.get('text_section'):
            print("\n.text Section:")
            print(f"  Virtual Address: 0x{data['text_section']['virtual_address']:08x}")
            print(f"  Size:            {data['text_section']['size_bytes']} bytes")
            print(f"  Output Path:     {data['text_section']['output_path']}")
        
        print("\nOutput Files Created:")
        for file_path in data.get('files_created', []):
            print(f"  - {file_path}")
        
        print("=" * 80 + "\n")
    
    def analyze(self) -> bool:
        """
        Execute full PE analysis workflow.
        
        Returns:
            True if analysis completed successfully, False otherwise
        """
        self.logger.info("Starting PE analysis workflow...")
        
        # Step 1: Validate input
        if not self.validate_input():
            return False
        
        # Step 2: Ensure output directory exists
        if not self.ensure_output_directory():
            return False
        
        # Step 3: Load PE file
        if not self.load_pe_file():
            return False
        
        # Step 4: Extract basic information
        architecture = self.get_architecture()
        pe_headers = self.extract_pe_headers()
        
        # Step 5: Enumerate all sections
        sections = self.enumerate_sections()
        
        # Step 6: Find and extract .text section
        text_section_info = self.find_text_section(sections)
        text_data = None
        text_output_path = None
        
        if text_section_info:
            text_data = self.extract_text_section(text_section_info)
            if text_data:
                text_output_path = self.save_text_section(text_data)
        
        # Step 7: Copy original PE file
        pe_copy_path = self.copy_original_pe()
        
        # Step 8: Build analysis data structure
        self.analysis_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "input_file": str(self.input_path),
            "architecture": architecture,
            "pe_headers": pe_headers,
            "sections": sections,
            "files_created": []
        }
        
        # Add .text section info if available
        if text_section_info and text_data:
            self.analysis_data["text_section"] = {
                "name": text_section_info["name"],
                "virtual_address": text_section_info["virtual_address"],
                "size_bytes": len(text_data),
                "output_path": os.path.basename(text_output_path) if text_output_path else None
            }
        
        # Track created files
        created_files = []
        if text_output_path:
            created_files.append(os.path.basename(text_output_path))
        if pe_copy_path:
            created_files.append(os.path.basename(pe_copy_path))
        
        # Step 9: Save JSON output
        json_path = self.save_json_output(self.analysis_data)
        if json_path:
            created_files.append(os.path.basename(json_path))
        
        self.analysis_data["files_created"] = created_files
        
        # Step 10: Print summary
        self.print_summary(self.analysis_data)
        
        # Step 11: Cleanup
        if self.pe:
            self.pe.close()
            self.logger.debug("PE file handle closed")
        
        self.logger.info("PE analysis completed successfully")
        return True


def run(input_path: str, output_dir: str, params: Optional[Dict[str, Any]] = None) -> bool:
    """
    Main entry point for rough.py compatibility.
    
    Args:
        input_path: Path to PE executable file
        output_dir: Directory to save extracted .text section and logs
        params: Optional parameters {"verbose": bool}
    
    Returns:
        True if analysis completed successfully, False otherwise
    """
    params = params or {}
    verbose = params.get("verbose", False)
    
    analyzer = PEAnalyzer(input_path, output_dir, verbose)
    return analyzer.analyze()


def main():
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="PE Analyzer - Extract and analyze PE file sections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i original.exe -o analysis_output
  %(prog)s --input C:\\samples\\target.exe --output C:\\results --verbose
        """
    )
    
    parser.add_argument('-i', '--input',required=True,metavar='PATH',help='Path to PE executable file')
    
    parser.add_argument( '-o', '--output',required=True,metavar='DIR',help='Output directory for analysis results')
    
    parser.add_argument( '-v', '--verbose',action='store_true',help='Enable verbose logging output')
    
    parser.add_argument( '--version',action='version',version='PE Analyzer v1.0.0')
    
    args = parser.parse_args()
    
    # Execute analysis
    success = run(args.input, args.output, {"verbose": args.verbose})
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()        