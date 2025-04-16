import argparse
import time

from flexfl.builtins.CommABC import CommABC
from flexfl.comms.MPI import MPI
from flexfl.comms.Zenoh import Zenoh
from flexfl.comms.Kafka import Kafka
from flexfl.comms.MQTT import MQTT


COMMS = {
    "mpi": MPI,
    "zenoh": Zenoh,
    "kafka": Kafka,
    "mqtt": MQTT
}

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
        node_id, data = comm.recv()
    end = time.time()
    print(f"Worker {comm.id} completed {iterations} iterations in {end - start:.3f} seconds")
    print("Exiting...")
    comm.close()
    print("Worker closed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--is_anchor", action="store_true", help="Run as anchor node", default=False)
    parser.add_argument("-c", "--comm", type=str, choices=["mpi", "zenoh", "kafka", "mqtt"], required=True, help="Communication method")
    parser.add_argument("-i", "--iterations", type=int, default=5000, help="Number of iterations for worker")
    args = parser.parse_args()
    comm: CommABC = COMMS[args.comm](is_anchor=args.is_anchor)
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