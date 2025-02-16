#!/bin/bash

# This is optional.
# GPT4All can sometimes max out memory and had lock a system with low RAM. This script attempts to prevent that by killing the GPT4All process "chat" if it detects memory usage is getting too high.

# Set the memory threshold (in percentage) to kill the "chat" process
MEMORY_THRESHOLD=85

# Function to get the current memory usage percentage (excluding swap)
get_memory_usage() {
  # Use `free` to get memory details, awk to calculate the percentage
  total_mem=$(free -m | grep Mem: | awk '{print $2}')
  used_mem=$(free -m | grep Mem: | awk '{print $3}')
  echo $(( 100 * used_mem / total_mem ))
}

# Function to handle graceful exit
graceful_exit() {
  echo -e "\n$(date) - Exiting gracefully..."
  exit 0
}

# Set up a trap to call graceful_exit on SIGINT, and ignore other signals
trap graceful_exit INT
trap 'sleep 1' HUP TERM


# Infinite loop to check memory usage every second
while true; do
  # Get current memory usage
  memory_usage=$(get_memory_usage)

  # If memory usage exceeds the threshold, kill the "chat" process and log it
  if [ "$memory_usage" -gt "$MEMORY_THRESHOLD" ]; then
    pkill -f "chat"
    echo "$(date) Memory overload: killed chat process."
  fi

  # Wait for 1 second before checking again
  sleep 1
done
