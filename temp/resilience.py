import sys
from dotenv import load_dotenv

sys.path.append(".")
load_dotenv()

import time

from comms.Zenoh import Zenoh

count = 0
z = Zenoh()

print(f"Node {z.id} started")

while True:
    time.sleep(5)
    count += 1

    if z.id == 0:
        workers = z.nodes - {0}
        for n in workers:
            z.send(n, b"work")
            print(f"Sent work to {n}")

        for n in workers:
            id_, data = z.recv()
            if data is None:
                print(f"Worker {id_} died")
            else:
                data = data.decode()
                print(f"Received {data} from {id_}")

    else:
        id_, data = z.recv()
        data = data.decode()
        print(f"Received {data} from {id_}")
        if count == 3:
            print("Worker died")
            z.close()
            exit(0)
        z.send(0, b"done")
        print("Sent done to 0")
