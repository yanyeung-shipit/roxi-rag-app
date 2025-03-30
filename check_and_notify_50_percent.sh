#!/bin/bash

# Script to check for 50% progress and send notifications
# This script will send an alert when the 50% target is reached
# Run with: ./check_and_notify_50_percent.sh

# Import utility functions
source ./utils/bash_colors.sh 2>/dev/null || true

# Path for tracking notification status
NOTIFICATION_SENT_FILE=".notification_sent"

# Check if notification has already been sent
notification_already_sent() {
  [ -f "$NOTIFICATION_SENT_FILE" ]
}

# Mark notification as sent
mark_notification_sent() {
  echo "$(date)" > "$NOTIFICATION_SENT_FILE"
}

# Draw a progress bar
draw_progress_bar() {
  local percent=$1
  local width=50
  local filled=$(echo "$percent * $width / 100" | bc -l | xargs printf "%.0f")
  local empty=$((width - filled))
  
  # Create the bar
  printf "["
  printf "%${filled}s" | tr ' ' '='
  printf ">"
  printf "%${empty}s" | tr ' ' ' '
  printf "] %.2f%%\n" "$percent"
}

# Show a notification banner
show_notification_banner() {
  local message=$1
  local length=${#message}
  local border=$(printf '%*s' "$length" | tr ' ' '=')
  
  echo -e "${BOLD_GREEN}"
  echo "$border"
  echo "$message"
  echo "$border"
  echo -e "${RESET}"
}

# Main function
main() {
  # Check if notification was already sent
  if notification_already_sent; then
    echo -e "${YELLOW}✓ Notification for 50% completion was already sent on:${RESET}"
    cat "$NOTIFICATION_SENT_FILE"
    return 0
  fi
  
  # Check current progress
  ./check_50_percent_progress.sh > /dev/null
  
  # If we reached 50%, send notification
  if [ $? -eq 0 ]; then
    # Get the exact progress percentage
    local result=$(python check_progress.py --json 2>/dev/null)
    local current_percent=$(echo "$result" | grep -o '"percent_processed": [0-9.]*' | grep -o '[0-9.]*')
    
    # Create celebratory banner
    echo -e "\n\n"
    show_notification_banner "🎉 TARGET REACHED: ${current_percent}% PROCESSED! 🎉"
    echo -e "\n"
    draw_progress_bar "$current_percent"
    echo -e "\n"
    echo -e "${BOLD_CYAN}The vector store rebuild has reached the 50% target!${RESET}"
    echo -e "${CYAN}Date: $(date)${RESET}"
    echo -e "${CYAN}Time to reach target: $(python -c 'import json; print(json.loads(open("continuous_processing.log").read())["elapsed_time"] if os.path.exists("continuous_processing.log") else "Unknown")')${RESET}"
    echo -e "\n"
    
    # Mark notification as sent to avoid duplicate notifications
    mark_notification_sent
    
    return 0
  else
    # Not yet at 50%
    echo -e "${YELLOW}Still working toward 50% target...${RESET}"
    return 1
  fi
}

# Run the main function
main