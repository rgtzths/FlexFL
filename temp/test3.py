import time
import sys

print("Hello, world!")
print(sys.argv[1:])

for _ in range(10):
    time.sleep(1)
    print("Still running...")