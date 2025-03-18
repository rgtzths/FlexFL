import subprocess
import time
import random
import sys
import os

PROGRAM = "python3 test3.py"
INTERVAL = 1
CHANCE = 0.1

process: subprocess.Popen = None

def terminate():
    if process:
        print("Terminating process...")
        process.terminate()
        process.wait()


def run_program(args: list) -> subprocess.Popen:
    return subprocess.Popen(
        PROGRAM.split() + args, 
        preexec_fn=os.setpgrp
    )


def main():
    global process
    process = run_program(sys.argv[1:])
    while True:
        if process.poll() is not None:
            print("Process terminated.")
            break
        if random.random() < CHANCE:
            print("Restarting process...")
            terminate()
            process = run_program(sys.argv[1:])
        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        terminate()