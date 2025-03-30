#!/bin/bash

# Script to check if we've reached 50% progress target
# This script will exit with code 0 if we've reached 50%, 1 otherwise

# Import utility functions
source ./utils/bash_colors.sh 2>/dev/null || true

# Format percentages for display
format_percent() {
  local percent=$1
  # Format to 2 decimal places and add % sign
  printf "%.2f%%" "$percent"
}

# Main check function
check_progress() {
  # Run the progress check Python script with JSON output
  local result=$(python check_progress.py --json 2>/dev/null)
  
  # Check if the command succeeded
  if [ $? -ne 0 ]; then
    echo "${RED}Failed to run progress check script${RESET}"
    return 1
  fi
  
  # Extract current percentage
  local current_percent=$(echo "$result" | grep -o '"percent_processed": [0-9.]*' | grep -o '[0-9.]*')
  
  # Check if we found a percentage
  if [ -z "$current_percent" ]; then
    echo "${RED}Failed to parse current percentage${RESET}"
    return 1
  fi
  
  # Format for display
  local formatted_percent=$(format_percent "$current_percent")
  
  # Display progress
  echo "${CYAN}Current progress: ${YELLOW}$formatted_percent${RESET}"
  
  # Convert to a numeric value for comparison
  current_percent=$(echo "$current_percent" | sed 's/,/./g')  # Handle locales that use comma
  
  # Check if we're at 50% or higher
  if (( $(echo "$current_percent >= 50.0" | bc -l) )); then
    echo "${GREEN}🎉 Target of 50% has been reached!${RESET}"
    return 0
  else
    echo "${YELLOW}Still working toward 50% target...${RESET}"
    return 1
  fi
}

# Call the main function and return its exit code
check_progress
exit $?