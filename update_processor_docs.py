#!/usr/bin/env python3
"""
Update Processor Documentation

This script automatically scans for processor-related scripts and updates
the documentation in PROCESSOR_REFERENCE.md with current information.
It helps keep the central reference documentation up-to-date.
"""

import os
import sys
import re
import argparse
from datetime import datetime
from collections import defaultdict

# Processor categories
CATEGORIES = {
    "primary": {
        "title": "PRIMARY RECOMMENDED PROCESSORS",
        "scripts": [
            "processors/adaptive_processor.py",
            "batch_rebuild_to_target.py",
            "add_single_chunk.py"
        ]
    },
    "db_handling": {
        "title": "DATABASE CONNECTION HANDLING",
        "scripts": [
            "enhanced_batch_processor.py",
            "robust_process_to_50_percent.py",
            "enhanced_process_to_50_percent.py"
        ]
    },
    "monitoring": {
        "title": "MONITORING AND MANAGEMENT SCRIPTS",
        "scripts": [
            "check_processor_progress.py",
            "monitor_and_restart.sh",
            "enhanced_monitor_and_restart.sh",
            "check_and_restart_processor.sh"
        ]
    },
    "specialized": {
        "title": "SPECIALIZED PROCESSING SCRIPTS",
        "scripts": [
            "process_to_50_percent.py",
            "process_to_75_percent.py",
            "process_to_sixty_six_percent.py",
            "fast_chunk_processor.py",
            "parallel_chunk_processor.py",
            "direct_process_chunk.py"
        ]
    },
    "legacy": {
        "title": "LEGACY/REDUNDANT SCRIPTS",
        "replacements": {
            "simple_chunk_processor.py": "add_single_chunk.py",
            "process_multiple_direct.py": "batch_process_chunks.py",
            "run_chunk_processor.py": "processors/run_batch_to_40_percent.sh",
            "process_one_chunk.py": "add_single_chunk.py",
            "process_next_ten.py": "batch_process_chunks.py",
            "test_process_for_5min.py": "N/A - testing script only",
            "simplified_processor.py": "adaptive_processor.py"
        }
    }
}

def get_script_description(script_path):
    """Extract a concise description from a script file."""
    if not os.path.exists(script_path):
        return "File not found"
    
    try:
        with open(script_path, 'r') as f:
            content = f.read(2000)  # Read first 2000 characters to look for docstring
            
        if script_path.endswith('.py'):
            # Extract Python docstring
            if '"""' in content:
                start = content.find('"""') + 3
                end = content.find('"""', start)
                if end > start:
                    docstring = content[start:end].strip()
                    lines = docstring.split('\n')
                    # Return first non-empty line
                    for line in lines:
                        if line.strip():
                            return line.strip()
            return "Python script"
            
        elif script_path.endswith('.sh'):
            # Extract comment description
            lines = content.split('\n')
            for line in lines:
                if line.strip().startswith('#') and len(line.strip()) > 2:
                    return line.strip('# \n')
            return "Shell script"
            
        else:
            return "Unknown file type"
            
    except Exception as e:
        return f"Error reading file: {str(e)}"

def find_all_processor_scripts():
    """Find all processor-related scripts in the project."""
    # Find Python processors
    py_cmd = "find . -type f -name '*process*.py' -not -path '*/.cache/*' -not -path '*/.pythonlibs/*'"
    py_scripts = os.popen(py_cmd).read().strip().split('\n')
    
    # Find shell scripts for monitoring
    sh_cmd = "find . -type f -name '*monitor*.sh' -o -name '*restart*.sh'"
    sh_scripts = os.popen(sh_cmd).read().strip().split('\n')
    
    all_scripts = py_scripts + sh_scripts
    return [s.lstrip('./') for s in all_scripts if s and not s.startswith('./.')]

def categorize_script(script_name):
    """Determine the category for a script."""
    for category, data in CATEGORIES.items():
        if category == "legacy" and script_name in data["replacements"]:
            return category
        elif "scripts" in data and script_name in data["scripts"]:
            return category
    
    # If not found in any category
    return "other"

def generate_script_table(scripts, category):
    """Generate a markdown table for a category of scripts."""
    lines = []
    lines.append(f"## {CATEGORIES[category]['title']}\n")
    
    if category == "legacy":
        lines.append("| Script | Replaced By | Notes |")
        lines.append("|--------|-------------|-------|")
        
        for script in scripts:
            replacement = CATEGORIES["legacy"]["replacements"].get(script, "Unknown")
            description = get_script_description(script) if os.path.exists(script) else "Not found"
            lines.append(f"| **{script}** | {replacement} | {description} |")
    else:
        lines.append("| Script | Purpose | When to Use | Special Features |")
        lines.append("|--------|---------|-------------|-----------------|")
        
        for script in scripts:
            description = get_script_description(script) if os.path.exists(script) else "Not found"
            special = ""
            when_to_use = ""
            
            # Add special notes for certain categories
            if category == "primary":
                if "adaptive" in script:
                    special = "Auto-adjusts batch size, deep sleep mode"
                    when_to_use = "**DEFAULT CHOICE** for most scenarios"
                elif "batch_rebuild" in script:
                    special = "Fast processing with configurable batch size"
                    when_to_use = "High-resource environments"
                elif "add_single_chunk" in script:
                    special = "Minimal resource usage, highest reliability"
                    when_to_use = "When extreme reliability is needed"
            
            elif category == "db_handling":
                when_to_use = "If PostgreSQL SSL connection errors occur"
                
            elif category == "monitoring":
                when_to_use = "For continuous process supervision"
            
            # Format the script name
            script_display = f"**{script}**" if category == "primary" else script
            
            lines.append(f"| {script_display} | {description} | {when_to_use} | {special} |")
    
    lines.append("")  # Add an empty line at the end
    return "\n".join(lines)

def generate_documentation(scripts):
    """Generate complete documentation for all processors."""
    # Group scripts by category
    categorized = defaultdict(list)
    uncategorized = []
    
    for script in scripts:
        category = categorize_script(script)
        if category == "other":
            uncategorized.append(script)
        else:
            categorized[category].append(script)
    
    # Generate documentation parts
    doc_parts = []
    
    # Header
    doc_parts.append("# ROXI Processing Scripts Reference Guide\n")
    doc_parts.append(f"*Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
    doc_parts.append("This document serves as a central reference for all processing scripts in the ROXI system. It categorizes scripts by functionality and provides information about when to use each one.\n")
    
    # Generate tables for each category
    for category in ["primary", "db_handling", "monitoring", "specialized", "legacy"]:
        if category in categorized and categorized[category]:
            doc_parts.append(generate_script_table(categorized[category], category))
    
    # Other scripts
    if uncategorized:
        doc_parts.append("## OTHER SCRIPTS\n")
        doc_parts.append("| Script | Description |")
        doc_parts.append("|--------|-------------|")
        
        for script in sorted(uncategorized):
            description = get_script_description(script) if os.path.exists(script) else "Not found"
            doc_parts.append(f"| {script} | {description} |")
        
        doc_parts.append("")
    
    # Best practices section
    doc_parts.append("## Best Practices\n")
    doc_parts.append("1. **Always Check the README First**: Before creating a new script, check this reference guide and the processors/README.md file.\n")
    doc_parts.append("2. **Use the adaptive_processor.py**: This is our most sophisticated processor that handles resource management and includes all essential features.\n")
    doc_parts.append("3. **Handle Database Errors**: If encountering PostgreSQL SSL connection errors, use the enhanced_batch_processor.py.\n")
    doc_parts.append("4. **Monitoring**: Always use a monitoring script when running long batch processes.\n")
    doc_parts.append("5. **Progressive Goals**: Target smaller percentages first (40-50%) before attempting larger goals (75-100%).\n")
    doc_parts.append("6. **Documentation**: When creating a new script, document it here for future reference.\n")
    
    return "\n".join(doc_parts)

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Update processor documentation")
    parser.add_argument('--dry-run', action='store_true', help='Print documentation instead of updating file')
    parser.add_argument('--output', type=str, default='PROCESSOR_REFERENCE.md', help='Output file path')
    
    args = parser.parse_args()
    
    # Find all scripts
    scripts = find_all_processor_scripts()
    print(f"Found {len(scripts)} processor-related scripts")
    
    # Generate documentation
    documentation = generate_documentation(scripts)
    
    if args.dry_run:
        print("\n=== GENERATED DOCUMENTATION ===\n")
        print(documentation)
    else:
        with open(args.output, 'w') as f:
            f.write(documentation)
        print(f"Updated documentation in {args.output}")

if __name__ == "__main__":
    main()