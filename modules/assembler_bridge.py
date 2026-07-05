#!/usr/bin/env python3
"""
Assembler Bridge v3 - Handles the actual transformation format
Converts transformations with applied=true to patcher format
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("AssemblerBridge")


class AssemblerBridgeV3:
    """Converts transformation format to patcher format."""
    
    def __init__(self):
        self.stats = {
            "total": 0,
            "applied": 0,
            "skipped": 0,
            "by_reason": {}
        }
    
    def convert_transformations(self, transformed_json: Path) -> Dict:
        """
        Convert transformation format to patcher format.
        
        """
        logger.info(f"Loading: {transformed_json}")
        
        with open(transformed_json) as f:
            data = json.load(f)
        
        # Extract transformations array
        if isinstance(data, dict):
            transformations = data.get('transformations', [])
            metadata = data.get('metadata', {})
        elif isinstance(data, list):
            transformations = data
            metadata = {}
        else:
            logger.error(f"Unexpected JSON format: {type(data)}")
            return {"transformations": []}
        
        logger.info(f"Processing {len(transformations)} transformations...")
        if metadata:
            logger.info(f"Metadata: {metadata}")
        
        patches = []
        
        for t in transformations:
            self.stats["total"] += 1
            
            # Check if transformation was actually applied
            applied = t.get('applied', False)
            reason = t.get('reason', 'unknown')
            
            if not applied:
                self.stats["skipped"] += 1
                self.stats["by_reason"][reason] = self.stats["by_reason"].get(reason, 0) + 1
                continue
            
            # Extract patch data
            address = t.get('address')
            original_bytes = t.get('original_bytes', '')
            new_bytes = t.get('new_bytes', '')
            
            if not all([address is not None, original_bytes, new_bytes]):
                logger.warning(f"Incomplete transformation at {address}")
                continue
            
            # Check if bytes actually changed
            if original_bytes == new_bytes:
                logger.debug(f"No change at 0x{address:x}, skipping")
                continue
            
            # Create patch entry
            patch = {
                "address": address,
                "new_bytes": new_bytes,
                "original_bytes": original_bytes,
                "applied": True
            }
            
            # Optional: include ASM for debugging
            if 'new_asm' in t:
                patch['asm'] = t['new_asm']
            
            patches.append(patch)
            self.stats["applied"] += 1
            
            if self.stats["applied"] <= 10:  # Log first 10
                logger.info(
                    f"Patch {len(patches)}: 0x{address:x} "
                    f"{original_bytes} → {new_bytes}"
                )
        
        # Report
        logger.info("=" * 60)
        logger.info("CONVERSION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total transformations:  {self.stats['total']}")
        logger.info(f"Applied (changed):      {self.stats['applied']}")
        logger.info(f"Skipped (unchanged):    {self.stats['skipped']}")
        
        if self.stats["by_reason"]:
            logger.info("\nSkipped by reason:")
            for reason, count in sorted(self.stats["by_reason"].items()):
                logger.info(f"  {reason:20s}: {count}")
        
        logger.info(f"\nPatches generated:      {len(patches)}")
        logger.info("=" * 60)
        
        return {
            "transformations": patches,
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "stats": self.stats,
                "original_metadata": metadata
            }
        }
    
    def save(self, data: Dict, output_path: Path):
        """Save assembled patches."""
        if output_path.is_dir():
            output_file = output_path / "assembled_patches.json"
        else:
            output_file = output_path
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved: {output_file}")


def main():
    parser = argparse.ArgumentParser( description="Convert transformation format to patcher format (v3)" )

    parser.add_argument('--input',required=True,type=Path,help='transformed_instructions.json from transformation stage')

    parser.add_argument( '--output',required=True,type=Path,help='Output path for assembled_patches.json')
    
    parser.add_argument('-v', '--verbose',action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Process
    bridge = AssemblerBridgeV3()
    patches = bridge.convert_transformations(args.input)
    bridge.save(patches, args.output)
    
    logger.info("Conversion complete!")


if __name__ == "__main__":
    main()