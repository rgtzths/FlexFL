import argparse
import time

from flexfl.builtins.CommABC import CommABC
from flexfl.comms.Zenoh import Zenoh
from flexfl.comms.Kafka import Kafka
from flexfl.comms.MQTT import MQTT


COMMS = {
    "zenoh": Zenoh,
    "kafka": Kafka,
    "mqtt": MQTT
}

PAYLOAD = b"a" * 1024  # 1KB payload

def master():
    while True:
        node_id, data = comm.recv()
        if data is None:
            print(f"Node {node_id} disconnected")
        else:
            comm.send(node_id, PAYLOAD)

def worker(iterations):
    print("Starting...")
    start = time.time()
    for _ in range(iterations):
        comm.send(0, PAYLOAD)
        node_id, data = comm.recv()
    end = time.time()
    print(f"Worker {comm.id} completed {iterations} iterations in {end - start:.3f} seconds")
    print("Exiting...")
    comm.close()
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--is_anchor", action="store_true", help="Run as anchor node", default=False)
    parser.add_argument("-c", "--comm", type=str, choices=["zenoh", "kafka", "mqtt"], default="zenoh", help="Communication method")
    parser.add_argument("-i", "--iterations", type=int, default=1000, help="Number of iterations for worker")
    args = parser.parse_args()
    comm: CommABC = COMMS[args.comm](is_anchor=args.is_anchor)
    print(f"Communication method: {args.comm}")
    print(f"Node ID: {comm.id}")
    if args.is_anchor:
        try:
            master()
        except KeyboardInterrupt:
            print("Master interrupted")
            comm.close()
    else:
        worker(args.iterations)