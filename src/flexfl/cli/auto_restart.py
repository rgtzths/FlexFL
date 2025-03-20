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


def run_program(program, args: list) -> subprocess.Popen:
    return subprocess.Popen(
        program.split() + args, 
        preexec_fn=os.setpgrp
    )


def run(interval, chance, program, args):
    process = None
    try:
        process = run_program(program, args)
        while True:
            if process.poll() is not None:
                print("Process terminated.")
                break
            if random.random() < chance:
                print("Restarting process...")
                terminate(process)
                process = run_program(program, args)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nForcing end...")
        terminate(process)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", type=int, help="Interval in seconds", default=1)
    parser.add_argument("-c", type=float, help="Chance of restart", default=0.1)
    parser.add_argument("-p", type=str, help="Program to run", required=True)
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Program arguments")
    args = parser.parse_args()
    run(args.i, args.c, args.p, args.args)


if __name__ == "__main__":
    main()

    