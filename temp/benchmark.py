import numpy as np
import random
import time
import sys
from dotenv import load_dotenv
import pickle

sys.path.append(".")
load_dotenv()

import argparse
from flexfl.builtins.CommABC import CommABC
from flexfl.comms.Zenoh import Zenoh
from flexfl.comms.Kafka import Kafka
from flexfl.comms.MQTT import MQTT
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

payload = np.array([random.randint(0, 100) for _ in range(10000)], dtype=np.float32)
payload = pickle.dumps(payload)

if c.id == 0:
    while True:
        time.sleep(1)
        if len(c.nodes) == 2:
            break
    print(f"Starting benchmark: Ping Pong with {LOOPS} loops")
    start = time.time()

    for _ in range(LOOPS):
        c.send(1, payload)
        _, data = c.recv()
    end = time.time()
    print(f"Time taken: {end - start}")
    print(f"Avg time for each msg: {(end - start) / (LOOPS * 2)}")

else:
    for _ in range(LOOPS):
        _, data = c.recv()
        c.send(0, payload)

c.close()

    