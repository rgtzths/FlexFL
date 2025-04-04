
from flexfl.builtins.Results import Results

from rich.console import Console
from rich.table import Table

console = Console()

f = Results.get_last_folder()

r = Results(f)

# print(r.n_workers)

# console.print_json(data=r.log2path)
# console.print_json(data=r.log2node)

validations = r.get_validations()   # start, end, duration
failures = r.get_failures()         # nid, lid, timestamp
leaves = r.get_leaves()             # nid, lid, timestamp
work_times = r.get_work_times()     # nid, lid, start, end, duration
comms = r.get_comms()               # send_nid, send_lid, recv_nid, recv_lid, start, end, duration (ms), payload (bytes)
metrics = r.get_metrics()           # epoch, time, loss, mcc, acc, f1

data = metrics

table = Table()
for col in data.columns:
    table.add_column(col, justify="left", no_wrap=True)
for index, row in data.iterrows():
    table.add_row(*[str(row[col]) for col in data.columns])
console.print(table)

