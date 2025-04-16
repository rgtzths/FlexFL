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


def master():
    while True:
        node_id, data = comm.recv()
        if data is None:
            print(f"Node {node_id} disconnected")
        else:
            comm.send(node_id, b"ack")

def worker():
    comm.send(0, b"Hello from worker")
    node_id, data = comm.recv()
    time.sleep(1)
    print("Exiting...")
    comm.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--is_anchor", action="store_true", help="Run as anchor node", default=False)
    parser.add_argument("--comm", type=str, choices=["zenoh", "kafka", "mqtt"], default="zenoh", help="Communication method")
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
        worker()