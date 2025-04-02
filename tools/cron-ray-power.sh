#!/bin/bash

# --- Configuration ---
WORK_DIR="/home/ubuntu/Repos/pypowerwall"
VENV_DIR="$WORK_DIR/env"
PYTHON_SCRIPT="$WORK_DIR/tools/ray-run.py"
# PYTHON_MODE_SCRIPT="$WORK_DIR/tools/set-mode.py"
# PYTHON_RESERVE_SCRIPT="$WORK_DIR/tools/set-reserve.py"
LOG_FILE="$WORK_DIR/tools/log_debug.log" # Example log file for set-mode

# --- Activate Virtual Environment ---
echo "Activating virtual environment: $VENV_DIR"
source "$VENV_DIR/bin/activate"

# --- Run Python Script ---
echo "Running Python script: python3 $PYTHON_RESERVE_SCRIPT --debug > $LOG_FILE"
python3 "$PYTHON_MODE_SCRIPT" >> "$LOG_FILE"

# --- Deactivate Virtual Environment ---
deactivate

echo "Python script execution finished. Output logged to: $LOG_FILE"

exit 0
