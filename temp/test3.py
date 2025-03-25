import time
import sys
import logging
import signal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', filename='test.log')

def handle_terminate(signal, frame):
    logging.info("Terminating...")
    logging.shutdown()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_terminate) # terminate
signal.signal(signal.SIGINT, handle_terminate)  # interrupt


print("Hello, world!")
print(sys.argv[1:])

for _ in range(10):
    time.sleep(1)
    logging.info("Still running...")
    print("Still running...")