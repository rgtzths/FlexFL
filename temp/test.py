from datetime import datetime

t1 = 1743006632.1899338
t2 = 1743006632.1900487

t1 = datetime.fromtimestamp(t1)
t2 = datetime.fromtimestamp(t2)

diff = t2 - t1
print(diff.total_seconds() * 1000)