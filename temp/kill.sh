#!/bin/bash

PYTHON_SCRIPT="temp/resilience.py"

# Function to clean up on exit
cleanup() {
    echo "Stopping script..."
    kill $PID
    wait $PID 2>/dev/null
    exit 0
}


trap cleanup SIGINT SIGTERM

# Start the Python script
python "$PYTHON_SCRIPT" &
PID=$!

# Monitor the Python process
while kill -0 $PID 2>/dev/null; do
    sleep 1

    # If the process has exited, exit the script
    if ! kill -0 $PID 2>/dev/null; then
        echo "Python script finished. Exiting..."
        exit 0
    fi

    # 1% chance to restart the process
    if [ $((RANDOM % 30)) -eq 0 ]; then
        echo "Restarting process..."
        kill $PID
        wait $PID 2>/dev/null
        python "$PYTHON_SCRIPT" &
        PID=$!
    fi
done
