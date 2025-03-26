import subprocess
import time
import random
import os
import argparse

def terminate(process: subprocess.Popen):
    if process:
        print("Terminating process...")
        process.terminate()
        process.wait()


def run_program(args: list) -> subprocess.Popen:
    return subprocess.Popen(
        args, 
        preexec_fn=os.setpgrp
    )


def run(interval, chance, args):
    process = None
    try:
        process = run_program(args)
        while True:
            if process.poll() is not None:
                print("Process terminated.")
                break
            if random.random() < chance:
                print("Restarting process...")
                terminate(process)
                process = run_program(args)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nForcing end...")
        terminate(process)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interval", type=int, help="Interval in seconds", default=1)
    parser.add_argument("-c", "--chance",type=float, help="Chance of restart", default=0.1)
    parser.add_argument("-s", "--seed", type=int, help="Seed for random number generator", default=42)
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Program arguments")
    args = parser.parse_args()
    if len(args.args) < 1:
        parser.error("Please provide a program to run.")
        exit(1)
    random.seed(args.seed)
    run(args.interval, args.chance, args.args)


if __name__ == "__main__":
    main()

    