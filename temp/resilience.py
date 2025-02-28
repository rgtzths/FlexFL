import sys
from dotenv import load_dotenv

sys.path.append(".")
load_dotenv()

import time

import argparse
from comms.Zenoh import Zenoh
from comms.Kafka import Kafka
from comms.MQTT import MQTT

COMMS = {
    "zenoh": Zenoh,
    "kafka": Kafka,
    "mqtt": MQTT,
}

parser = argparse.ArgumentParser()
parser.add_argument("--comms", type=str, default="zenoh")
parser.add_argument("--anchor", action=argparse.BooleanOptionalAction, default=False)
args = parser.parse_args()
c = COMMS[args.comms](is_anchor=args.anchor)
print(f"Node {c.id} started")

count = 0
while True:
    time.sleep(5)
    # continue
    count += 1

    if c.id == 0:
        workers = c.nodes - {0}
        for n in workers:
            c.send(n, b"work")
            print(f"Sent work to {n}")

        for n in workers:
            id_, data = c.recv()
            if data is None:
                print(f"Worker {id_} died")
            else:
                data = data.decode()
                print(f"Received {data} from {id_}")

    else:
        id_, data = c.recv()
        data = data.decode()
        print(f"Received {data} from {id_}")
        if count == 3:
            print("Worker died")
            c.close()
            exit(0)
        c.send(0, b"done")
        print("Sent done to 0")
