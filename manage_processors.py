#!/usr/bin/env python3
"""
Script Management Tool for ROXI

This utility helps manage the numerous processing scripts in the ROXI system:
- Lists all processing scripts with categorization
- Identifies potentially redundant scripts 
- Analyzes script functionality
- Recommends the most appropriate scripts for different purposes
"""

import os
import sys
import re
import glob
import argparse
from datetime import datetime
from collections import defaultdict

# Categories for script classification
CATEGORIES = {
    "primary": {
        "patterns": ["adaptive_processor", "batch_rebuild", "add_single_chunk"],
        "description": "Primary recommended processors"
    },
    "batch": {
        "patterns": ["batch", "process_multiple", "chunks"],
        "description": "Batch processing scripts"
    },
    "single": {
        "patterns": ["single", "one_chunk", "process_one"],
        "description": "Single chunk processors"
    },
    "target": {
        "patterns": ["50_percent", "75_percent", "66_percent", "to_target"],
        "description": "Target percentage processors"
    },
    "db": {
        "patterns": ["connection", "database", "robust", "enhanced"],
        "description": "Database connection handlers"
    },
    "monitor": {
        "patterns": ["monitor", "check", "restart", "progress"],
        "description": "Monitoring and progress scripts"
    },
    "utility": {
        "patterns": ["util", "backup", "clean", "fix", "check", "diagnose"],
        "description": "Utility scripts"
    }
}

# Scripts known to be redundant
REDUNDANT_SCRIPTS = [
    "simple_chunk_processor.py",
    "process_multiple_direct.py",
    "run_chunk_processor.py",
    "process_one_chunk.py",
    "process_next_ten.py",
    "test_process_for_5min.py",
    "simplified_processor.py"
]

def gather_processing_scripts():
    """Find all processing-related scripts in the project."""
    # Find Python processors
    py_scripts = glob.glob("*.py") + glob.glob("processors/*.py")
    py_scripts = [s for s in py_scripts if any(kw in s.lower() for kw in 
                  ["process", "chunk", "batch", "vector", "monitor", "check"])]
    
    # Find shell scripts
    sh_scripts = glob.glob("*.sh") + glob.glob("processors/*.sh")
    
    # Combine and sort
    all_scripts = sorted(py_scripts + sh_scripts)
    return all_scripts

def categorize_scripts(scripts):
    """Categorize scripts by their type and function."""
    categorized = defaultdict(list)
    
    for script in scripts:
        # Check if it's in the redundant list
        if os.path.basename(script) in REDUNDANT_SCRIPTS:
            categorized["redundant"].append(script)
            continue
            
        # Check against category patterns
        assigned = False
        for category, data in CATEGORIES.items():
            if any(pattern in script.lower() for pattern in data["patterns"]):
                categorized[category].append(script)
                assigned = True
                break
        
        # If not assigned to any category
        if not assigned:
            categorized["other"].append(script)
    
    return categorized

def get_script_description(script_path):
    """Extract the description from a script file."""
    if not os.path.exists(script_path):
        return "File not found"
    
    try:
        with open(script_path, 'r') as f:
            content = f.read(2000)  # Read first 2000 characters
            
        if script_path.endswith('.py'):
            # Extract Python docstring
            if '"""' in content:
                start = content.find('"""') + 3
                end = content.find('"""', start)
                if end > start:
                    docstring = content[start:end].strip()
                    # Get the first paragraph or first sentence
                    first_line = docstring.split('\n\n')[0].split('.')[0]
                    return first_line.strip() + '.'
            return "Python script"
            
        elif script_path.endswith('.sh'):
            # Extract comment description
            lines = content.split('\n')
            for line in lines[:10]:  # Check first 10 lines
                if line.strip().startswith('#') and len(line.strip()) > 2:
                    return line.strip('# \n')
            return "Shell script"
            
        else:
            return "Unknown file type"
            
    except Exception as e:
        return f"Error reading file: {str(e)}"

def print_script_categories(categories):
    """Print scripts by category in a readable format."""
    print(f"\n{'=' * 80}")
    print(f"ROXI SCRIPT MANAGEMENT REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 80}\n")
    
    # Print summary counts
    total_scripts = sum(len(scripts) for scripts in categories.values())
    print(f"Total scripts found: {total_scripts}")
    for category, scripts in categories.items():
        if scripts:
            if category in CATEGORIES:
                desc = CATEGORIES[category]["description"]
            elif category == "redundant":
                desc = "Redundant/deprecated scripts"
            else:
                desc = "Other scripts"
            print(f"- {desc}: {len(scripts)}")
    print()
    
    # Print each category
    for category, scripts in categories.items():
        if not scripts:
            continue
            
        if category in CATEGORIES:
            print(f"\n## {CATEGORIES[category]['description'].upper()}")
        elif category == "redundant":
            print("\n## REDUNDANT/DEPRECATED SCRIPTS")
        else:
            print("\n## OTHER SCRIPTS")
        
        for script in scripts:
            description = get_script_description(script)
            print(f"- {script}")
            print(f"  {description}")
        
    # Provide recommendations if redundant scripts are found
    if categories["redundant"]:
        print("\n## REDUNDANCY RECOMMENDATIONS")
        print("The following scripts have been identified as redundant and could be moved to legacy/:")
        for script in categories["redundant"]:
            print(f"- {script}")
        print("\nTo move these scripts to the legacy directory, run:")
        print("  python cleanup_redundant_scripts.py")

def generate_recommendations():
    """Generate recommendations for script usage."""
    print("\n## RECOMMENDED SCRIPTS BY TASK")
    
    tasks = [
        ("Regular processing", "processors/adaptive_processor.py", 
         "Auto-adjusts resource usage, handles deep sleep, and includes all features"),
        
        ("Fastest processing", "batch_rebuild_to_target.py", 
         "Processes chunks in batches with minimal overhead"),
        
        ("Most reliable processing", "add_single_chunk.py", 
         "Processes one chunk at a time with maximum reliability"),
        
        ("PostgreSQL SSL connection issues", "enhanced_batch_processor.py", 
         "Includes connection pooling and retry mechanisms"),
        
        ("Monitoring long-running processors", "enhanced_monitor_and_restart.sh", 
         "Provides exponential backoff and detailed logging"),
        
        ("Checking progress", "check_processor_progress.py", 
         "Shows detailed progress statistics")
    ]
    
    for task, script, description in tasks:
        print(f"- {task}:")
        print(f"  → Use {script}")
        print(f"    {description}")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="ROXI Script Management Tool")
    parser.add_argument('--update-docs', action='store_true', help='Update the PROCESSOR_REFERENCE.md documentation')
    
    args = parser.parse_args()
    
    # Update documentation if requested
    if args.update_docs:
        print("Updating processor documentation...")
        os.system("python update_processor_docs.py")
        return
    
    # Find all scripts
    scripts = gather_processing_scripts()
    
    # Categorize them
    categories = categorize_scripts(scripts)
    
    # Print categorized scripts
    print_script_categories(categories)
    
    # Generate recommendations
    generate_recommendations()
    
    # Final note
    print("\n## NEXT STEPS")
    print("1. To move redundant scripts to legacy/ directory:")
    print("   python cleanup_redundant_scripts.py")
    print("2. To update processor documentation:")
    print("   python update_processor_docs.py")
    print("3. To clean up the vector store:")
    print("   python clean_vector_store.py")
    print("\nFor more detailed information, see PROCESSOR_REFERENCE.md and DEVELOPMENT_CHECKLIST.md")

if __name__ == "__main__":
    main()