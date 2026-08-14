#!/usr/bin/env python3
"""
Integrated Orchestrator module for safe binary transformations.
Updated to support CFG swap engine with intelligent subset selection.
"""

import sys
import json
import argparse
import logging
import subprocess
from pathlib import Path
import os
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger("Orchestrator")

def load_config(config_path: Path) -> dict:
    """Load configuration from a JSON file."""
    with config_path.open('r') as f:
        return json.load(f)

def resolve_placeholders(text: str, context: dict) -> str:
    """Resolve placeholders in configuration strings."""
    if not isinstance(text, str):
        return text
    for key, value in context.items():
        text = text.replace(f"{{{key}}}", str(value))
    return text

def run_command(cmd):
    """Execute command and log output in real-time."""
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
        for line in proc.stdout:
            logger.info(line.strip())
    
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

def run_step(step_config: dict, context: dict):
    """Execute a single step from the configuration."""
    path_str = resolve_placeholders(step_config['path'], context)
    script_path = Path(path_str)
    
    # Handle case where extension is missing
    if not script_path.exists():
        if script_path.with_suffix('.py').exists():
            script_path = script_path.with_suffix('.py')
    
    if not script_path.exists():
        logger.error(f"Script not found: {script_path}")
        raise FileNotFoundError(f"Script not found: {script_path}")

    params = step_config.get('parameters', {})
    
    # Resolve parameter values
    resolved_params = {}
    for k, v in params.items():
        resolved_params[k] = resolve_placeholders(v, context)
        
    # Construct command line
    cmd = [sys.executable, str(script_path)]
    
    script_name = script_path.stem
    output_dir = Path(resolved_params['output_dir'])
    
    logger.info(f"==== Executing {script_name} ===")
    
    if script_name == 'parser_and_extractor':
        # CLI: -i INPUT -o OUTPUT_DIR -v
        cmd.extend(['-i', resolved_params['pe_file']])
        cmd.extend(['-o', str(output_dir)])
        if resolved_params.get('verbose'): cmd.append('-v')
        
        run_command(cmd)
        
        # Rename output to match config expectation
        default_out = output_dir / "text_section.bin"
        target_out = output_dir / resolved_params['output_file']
        if default_out.exists() and default_out != target_out:
            default_out.replace(target_out)
            logger.info(f"Renamed output to {target_out.name}")
            
    elif script_name == 'disassembler':
        # CLI: -i INPUT -o OUTPUT_DIR --filename NAME -v
        inp = output_dir / resolved_params['input_file']
        cmd.extend(['-i', str(inp)])
        cmd.extend(['-o', str(output_dir)])
        
        # Use filename arg to match config output
        out_filename = Path(resolved_params['output_file']).stem
        cmd.extend(['--filename', out_filename])
        
        if resolved_params.get('verbose'): cmd.append('-v')
        run_command(cmd)
        
    elif script_name == 'transformation_plan':
        # CLI: --input INPUT --output OUTPUT_DIR -v
        inp = output_dir / resolved_params['input_file']
        cmd.extend(['--input', str(inp)])
        cmd.extend(['--output', str(output_dir)])
        if resolved_params.get('verbose'): cmd.append('-v')

        run_command(cmd)
        
        # Rename output
        default_out = output_dir / "unified_transformation_plan.json"
        target_out = output_dir / resolved_params['output_file']
        if default_out.exists() and default_out != target_out:
            default_out.replace(target_out)
            logger.info(f"Renamed output to {target_out.name}")

    elif script_name == 'transformation':
        # CLI: --plan PLAN --exe EXE --output OUTPUT_DIR --count N
        plan = output_dir / resolved_params['plan_file']
        cmd.extend(['--plan', str(plan)])
        cmd.extend(['--exe', context['input_path']])
        cmd.extend(['--output', str(output_dir)])
        
        count = context.get('count')
        if count is not None:
            cmd.extend(['--count', str(count)])
        
        if context.get('divide_transform'):
            cmd.append('--divide-transform')
        

        run_command(cmd)
        
        # Rename output
        default_out = output_dir / "transformation_report.json"
        target_out = output_dir / resolved_params['output_file']
        if default_out.exists() and default_out != target_out:
            default_out.replace(target_out)
            logger.info(f"Renamed output to {target_out.name}")

    elif script_name == 'binary_patcher':
        # CLI: --exe EXE --transforms TRANSFORMS --output OUTPUT
        cmd.extend(['--exe', resolved_params['exe_file']])
        transforms = output_dir / resolved_params['transforms_file']
        cmd.extend(['--transforms', str(transforms)])
        out = output_dir / resolved_params['output_file']
        cmd.extend(['--output', str(out)])
        
        run_command(cmd)

    elif script_name == 'junk_inserter':
        # CLI: --disassembly JSON --input BIN --output OUT ...
        inp = output_dir / resolved_params['input_file']
        out = output_dir / resolved_params['output_file']
        
        cmd.extend(['--input', str(inp)])
        cmd.extend(['--output', str(out)])
        
        if 'junk_density' in resolved_params:
            cmd.extend(['--junk-density', str(resolved_params['junk_density'])])
        if 'junk_size_min' in resolved_params:
            cmd.extend(['--junk-size-min', str(resolved_params['junk_size_min'])])
        if 'junk_size_max' in resolved_params:
            cmd.extend(['--junk-size-max', str(resolved_params['junk_size_max'])])
            
        run_command(cmd)

    elif script_name == 'cfg_permutator' or script_name == 'cfg_swap_engine_production':
        # CLI: -i INPUT -o OUTPUT (old) or --input INPUT --output OUTPUT (new)
        inp = output_dir / resolved_params['input_file']
        out = output_dir / resolved_params['output_file']
        
        # Detect if script supports new features by checking if --enable-subset flag exists
        # Try new format first (works for both old name with new script, and new name)
        use_new_format = True  # Default to new format
        
        if use_new_format or script_name == 'cfg_swap_engine_production':
            # New script format (works even if file is named cfg_permutator.py)
            cmd.extend(['--input', str(inp)])
            cmd.extend(['--output', str(out)])
            
            # Enable intelligent subset mode by default
            if context.get('cfg_enable_subset', True):
                cmd.append('--enable-subset')
                logger.info("CFG subset mode: enabled")
            else:
                logger.info("CFG subset mode: disabled (all swaps)")
            
            # Optional: Manual subset percentage
            if context.get('cfg_subset_pct') is not None:
                cmd.extend(['--subset-pct', str(context['cfg_subset_pct'])])
                logger.info(f"CFG subset percentage: {context['cfg_subset_pct']*100:.0f}%")
            
            # Optional: Explicit seed
            if context.get('cfg_seed') is not None:
                cmd.extend(['--seed', str(context['cfg_seed'])])
                logger.info(f"CFG seed: {context['cfg_seed']}")
            
            # Count override (takes precedence over subset)
            if context.get('cfg_count') is not None:
                cmd.extend(['-n', str(context['cfg_count'])])
                logger.info(f"CFG count override: {context['cfg_count']}")
            
            # Verbosity
            if context.get('quiet'):
                cmd.append('-q')
            elif resolved_params.get('verbose'):
                cmd.append('-v')
        else:
            # Fallback: Very old cfg_permutator format (shouldn't reach here)
            cmd.extend(['-i', str(inp)])
            cmd.extend(['-o', str(out)])
            
            if context.get('cfg_count') is not None:
                cmd.extend(['-n', str(context['cfg_count'])])
                
            if resolved_params.get('verbose'): 
                cmd.append('-v')
        
        run_command(cmd)
        
        # Extract metadata if using new script
        if script_name == 'cfg_swap_engine_production':
            metadata_file = output_dir / 'cfg_swap_metadata.json'
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    
                    context['cfg_seed_used'] = metadata.get('seed')
                    context['cfg_swaps_performed'] = metadata.get('total_swaps')
                    context['cfg_subset_enabled'] = metadata.get('subset_enabled')
                    
                    logger.info(f"CFG swap metadata:")
                    logger.info(f"  Seed: {metadata.get('seed')}")
                    logger.info(f"  Swaps: {metadata.get('total_swaps')}")
                    logger.info(f"  Subset: {metadata.get('subset_enabled')}")
                except Exception as e:
                    logger.warning(f"Could not extract CFG swap metadata: {e}")

    elif script_name == 'signature_randomizer':
        # CLI: --input INPUT --output OUTPUT
        inp = output_dir / resolved_params['input_file']
        out = output_dir / resolved_params['output_file']
        cmd.extend(['--input', str(inp)])
        cmd.extend(['--output', str(out)])
        if resolved_params.get('verbose'): cmd.append('-v')
        
        run_command(cmd)

    else:
        logger.warning(f"Unknown module {script_name}, attempting generic execution")
        # Try to map generic parameters if possible, or just run
        run_command(cmd)

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Orchestrator for safe binary transformations."
    )
    parser.add_argument("--input", required=True, type=Path, help="Input Original binary file path")
    parser.add_argument("--config", required=True, type=Path, help="Configuration file path")
    parser.add_argument("--output", required=True, type=Path, help="Output directory")
    parser.add_argument("--count", type=int, default=None, help="Number of instruction transformations to apply (default: all)")
    parser.add_argument("--cfg-count", type=int, default=None, help="Number of CFG block swaps to apply (default: auto)")
    parser.add_argument("--cfg-enable-subset", "--enable-subset", action="store_true", default=True, help="Enable intelligent CFG subset (default: True)")
    parser.add_argument("--cfg-no-subset", "--no-subset", dest="cfg_enable_subset", action="store_false", help="Disable CFG subset, apply all swaps")
    parser.add_argument("--cfg-subset-pct", type=float, default=None, help="Manual CFG subset percentage (0.0-1.0)")
    parser.add_argument("--cfg-seed", type=int, default=None, help="CFG swap seed for reproducibility")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (minimal output)")
    parser.add_argument("--divide-transform", action="store_true", help="Enable distribution shuffling in transformation step")

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)

    if not args.config.exists():
        logger.error(f"Config file not found: {args.config}")
        sys.exit(1)
        
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    config = load_config(args.config)
    
    # Prepare context for placeholder resolution
    # base_path is the parent of the 'modules' directory
    base_path = Path(__file__).resolve().parent.parent
    
    context = {
        "input_path": str(args.input.resolve()),
        "input_name": args.input.stem,
        "output_dir": str(args.output.resolve()),
        "base_path": str(base_path),
        "count": args.count,
        "cfg_count": args.cfg_count,
        "cfg_enable_subset": args.cfg_enable_subset,
        "cfg_subset_pct": args.cfg_subset_pct,
        "cfg_seed": args.cfg_seed,
        "divide_transform": args.divide_transform,
        "quiet": args.quiet
    }
    
    # Ensure output directory exists
    args.output.mkdir(parents=True, exist_ok=True)
    
    # Add file handler to write logs to execution_logs.txt in output directory
    log_file = args.output / "execution_logs.txt"
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(file_handler)
    
    logger.info(f"Starting orchestration with config: {args.config.name}")
    logger.info(f"Base path: {base_path}")
    if args.cfg_enable_subset:
        logger.info(f"CFG subset mode: enabled")
    else:
        logger.info(f"CFG subset mode: disabled")
    
    # Iterate through techniques
    techniques = config.get('modules', {}).get('start', {}).get('techniques', [])
    
    for i, step in enumerate(techniques, 1):
        try:
            logger.info(f"Step {i}/{len(techniques)}")
            run_step(step, context)
        except Exception as e:
            logger.error(f"Pipeline failed at step {i}: {e}")
            sys.exit(1)
            
    logger.info("Orchestration completed successfully.")


if __name__ == "__main__":
    main()