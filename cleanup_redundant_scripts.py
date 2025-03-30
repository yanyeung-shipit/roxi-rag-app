#!/usr/bin/env python3
"""
Cleanup Redundant Scripts

This utility script moves identified redundant scripts to a legacy directory.
It preserves the scripts for reference while reducing clutter in the main directory.
"""

import os
import sys
import shutil
import argparse
from datetime import datetime

# List of scripts identified as redundant
REDUNDANT_SCRIPTS = [
    "simple_chunk_processor.py",
    "process_multiple_direct.py",
    "run_chunk_processor.py",
    "process_one_chunk.py",
    "process_next_ten.py",
    "test_process_for_5min.py",
    "simplified_processor.py"
]

def move_to_legacy(script_path, legacy_dir="legacy/processors", dry_run=False):
    """Move a script to the legacy directory."""
    if not os.path.exists(script_path):
        print(f"Script not found: {script_path}")
        return False
    
    # Create legacy directory if it doesn't exist
    os.makedirs(legacy_dir, exist_ok=True)
    
    # Destination path
    dest_path = os.path.join(legacy_dir, os.path.basename(script_path))
    
    # Don't overwrite existing files in legacy dir
    if os.path.exists(dest_path):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename, ext = os.path.splitext(os.path.basename(script_path))
        dest_path = os.path.join(legacy_dir, f"{filename}_{timestamp}{ext}")
    
    if dry_run:
        print(f"Would move {script_path} to {dest_path}")
        return True
    
    try:
        shutil.move(script_path, dest_path)
        print(f"Moved {script_path} to {dest_path}")
        return True
    except Exception as e:
        print(f"Error moving {script_path}: {str(e)}")
        return False

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Cleanup redundant scripts by moving them to a legacy directory")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be moved without actually moving')
    parser.add_argument('--legacy-dir', type=str, default='legacy/processors', help='Legacy directory to move scripts to')
    parser.add_argument('--scripts', nargs='+', help='Specific scripts to move (defaults to predefined list)')
    parser.add_argument('--yes', '-y', action='store_true', help='Proceed without confirmation')
    
    args = parser.parse_args()
    
    # Use provided scripts or default redundant scripts list
    scripts_to_move = args.scripts if args.scripts else REDUNDANT_SCRIPTS
    
    # Confirm with user
    print(f"\n=== SCRIPT CLEANUP {'(DRY RUN)' if args.dry_run else ''} ===")
    print(f"The following scripts will be moved to {args.legacy_dir}:")
    for script in scripts_to_move:
        print(f"  - {script}")
    
    if not args.dry_run and not args.yes:
        try:
            confirm = input("\nDo you want to proceed? (y/n): ")
            if confirm.lower() != 'y':
                print("Operation cancelled.")
                return
        except (EOFError, KeyboardInterrupt):
            print("\nNo input received. Use --yes to bypass confirmation.")
            return
    
    # Create the legacy directory
    os.makedirs(args.legacy_dir, exist_ok=True)
    
    # Create a README in the legacy directory
    readme_path = os.path.join(args.legacy_dir, "README.md")
    if not os.path.exists(readme_path) or args.dry_run:
        readme_content = f"""# Legacy Scripts

This directory contains scripts that have been moved from the main directory to reduce clutter.
These scripts are preserved for reference but are considered redundant with other scripts in the system.

Scripts were moved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Replacement Guide

| Legacy Script | Replacement |
|---------------|-------------|
| simple_chunk_processor.py | add_single_chunk.py |
| process_multiple_direct.py | batch_process_chunks.py |
| run_chunk_processor.py | processors/run_batch_to_40_percent.sh |
| process_one_chunk.py | add_single_chunk.py |
| process_next_ten.py | batch_process_chunks.py |
| test_process_for_5min.py | (Testing script only) |
| simplified_processor.py | adaptive_processor.py |

## Recommended Processors

The following processors are recommended for most uses:

1. processors/adaptive_processor.py - Resource-adaptive processing
2. batch_rebuild_to_target.py - Fast batch processing
3. add_single_chunk.py - Reliable single-chunk processing

For database connection issues, use enhanced_batch_processor.py.
"""
        if args.dry_run:
            print(f"Would create README at {readme_path}")
        else:
            with open(readme_path, 'w') as f:
                f.write(readme_content)
            print(f"Created README at {readme_path}")
    
    # Move each script
    moved_count = 0
    for script in scripts_to_move:
        if move_to_legacy(script, args.legacy_dir, args.dry_run):
            moved_count += 1
    
    # Summary
    print(f"\nOperation {'would have' if args.dry_run else ''} moved {moved_count} scripts to {args.legacy_dir}")
    if not args.dry_run and moved_count > 0:
        print(f"A README file with replacement information has been created in {args.legacy_dir}")

if __name__ == "__main__":
    main()