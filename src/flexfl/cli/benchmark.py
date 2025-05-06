import argparse
import time
import os

from flexfl.builtins.CommABC import CommABC
from flexfl.cli.utils import get_modules_and_args, load_class

PAYLOAD = b"a" * 1024  # 1KB payload

def master(comm: CommABC):
    while True:
        node_id, data = comm.recv()
        if data is None:
            print(f"Node {node_id} disconnected")
        else:
            comm.send(node_id, PAYLOAD)

def worker(comm: CommABC, iterations: int):
    print("Starting...")
    start = time.time()
    for _ in range(iterations):
        comm.send(0, PAYLOAD)
        comm.recv()
    end = time.time()
    print(f"Worker {comm.id} completed {iterations} iterations in {end - start:.3f} seconds")
    print("Exiting...")
    comm.close()
    print("Worker closed")


def main():

    FOLDERS: list[str] = [
        "comms",
    ]

    MODULES, _ = get_modules_and_args(FOLDERS)

    for m, classes in list(MODULES.items()):
        for class_name, path in list(classes.items()):
            MODULES[m][class_name.lower()] = path

    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--is_anchor", action="store_true", help="Run as anchor node", default=False)
    parser.add_argument("-c", "--comm", type=str, choices=MODULES["comms"].keys(), default="zenoh", help="Communication method")
    parser.add_argument("-i", "--iterations", type=int, default=5000, help="Number of iterations for worker")
    parser.add_argument("--ip", type=str, default="localhost", help="IP address of the master node")
    args = parser.parse_args()
    if "OMPI_COMM_WORLD_SIZE" in os.environ:
        args.comm = "MPI"
    comm: CommABC = load_class(MODULES["comms"][args.comm])(is_anchor=args.is_anchor, ip=args.ip)
    print(f"Communication method: {args.comm}")
    print(f"Node ID: {comm.id}")
    if comm.id == 0:
        try:
            master(comm)
        except KeyboardInterrupt:
            print("Master interrupted")
            comm.close()
    else:
        worker(comm, args.iterations)


if __name__ == "__main__":
    main()