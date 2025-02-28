import numpy as np
import random
import time
import sys
from dotenv import load_dotenv
import pickle

sys.path.append(".")
load_dotenv()

import argparse
from my_builtins.CommABC import CommABC
from comms.Zenoh import Zenoh
from comms.Kafka import Kafka
from comms.MQTT import MQTT
# from comms.MPI import MPI

COMMS = {
    "zenoh": Zenoh,
    "kafka": Kafka,
    "mqtt": MQTT,
    # "mpi": MPI,
}

LOOPS = 1000

parser = argparse.ArgumentParser()
parser.add_argument("--comms", type=str, default="zenoh")
parser.add_argument("--anchor", action=argparse.BooleanOptionalAction, default=False)
args = parser.parse_args()
c: CommABC  = COMMS[args.comms](is_anchor=args.anchor)
print(f"Node {c.id} started")

payload = np.array([random.randint(0, 100) for _ in range(10000)], dtype=np.uint8)
payload = pickle.dumps(payload)

if c.id == 0:
    while True:
        time.sleep(1)
        if len(c.nodes) == 2:
            break
    print("Starting benchmark")
    start = time.time()

    for _ in range(LOOPS):
        c.send(1, payload)
        _, data = c.recv()
    end = time.time()
    print(f"Time taken: {end - start}")

else:
    for _ in range(LOOPS):
        _, data = c.recv()
        c.send(0, payload)

c.close()

    