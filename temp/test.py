from datetime import datetime
import time

# Generate two ISO format timestamps with a small delay
timestamp1 = datetime.now().isoformat()
time.sleep(0.1)  # 100 milliseconds delay
timestamp2 = datetime.now().isoformat()

# Parse the timestamps back to datetime objects
dt1 = datetime.fromisoformat(timestamp1)
dt2 = datetime.fromisoformat(timestamp2)

# Calculate the difference in milliseconds
ms_diff = (dt2 - dt1).total_seconds() * 1000

print(f"Milliseconds difference: {ms_diff:.3f} ms")
