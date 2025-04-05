
from flexfl.builtins.Results import Results

from rich.console import Console
from rich.table import Table
import pandas as pd

console = Console()

def print_table(df: pd.DataFrame):
    table = Table()
    for col in df.columns:
        table.add_column(col, justify="left", no_wrap=True)
    for _, row in df.iterrows():
        table.add_row(*[f"{row[col]:.6f}" if isinstance(row[col], float) else str(row[col]) for col in df.columns])
    console.print(table)

f = Results.get_last_folder()

r = Results(f)

print(f"Results folder: {f}")
print(f"Number of workers: {r.n_workers}")
print(f"Start time: {r.start}")

# console.print_json(data=r.log2path)
# console.print_json(data=r.log2node)

validations = r.get_validations()   # start, end, duration
failures = r.get_failures()         # nid, lid, timestamp
leaves = r.get_leaves()             # nid, lid, timestamp
new_workers = r.get_new_workers()   # nid, lid, timestamp
work_times = r.get_work_times()     # nid, lid, start, end, duration
metrics = r.get_metrics()           # epoch, time, loss, mcc, acc, f1

wts = r.get_worker_time_status()

print_table(wts)


