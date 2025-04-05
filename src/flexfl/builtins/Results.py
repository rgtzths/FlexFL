from pathlib import Path
import pandas as pd
import json
from typing import Generator, Callable
from datetime import datetime
from functools import lru_cache
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class Results:

    BASE_DIR = "results"

    @staticmethod
    def get_all_folders() -> list[str]:
        folders = Path(Results.BASE_DIR).iterdir()
        folders = sorted(str(f) for f in folders if f.is_dir())
        return folders


    @staticmethod
    def get_last_folder() -> str:
        folders = Results.get_all_folders()
        if len(folders) == 0:
            return None
        return folders[-1]


    def __init__(self, results_folder: str) -> None:
        assert Path(results_folder).is_dir(), f"Results folder {results_folder} does not exist."
        self.results_folder = results_folder
        self.out = f"{results_folder}/_analysis"
        Path(self.out).mkdir(parents=True, exist_ok=True)
        self.logs: dict[int, list[dict]] = {}
        self.log2node: dict[int, int] = {}
        self.setup_paths()
        self.n_workers = len(set(self.log2node.values())) - 1


    def process_path(self, path_: Path, node_id: int = None) -> None:
        if path_.is_file() and path_.name.startswith("log_"):
            log_id = int(path_.name.split("_")[1].split(".")[0])
            if node_id is None:
                node_id = log_id
            self.log2node[log_id] = node_id
            self.logs[log_id] = []
            with open(str(path_), "r") as f:
                for line in f:
                    line = json.loads(line)
                    self.logs[log_id].append(line)


    def setup_paths(self):
        for path_ in Path(self.results_folder).iterdir():
            if path_.is_file():
                self.process_path(path_)
            elif path_.is_dir() and path_.name.startswith("worker_"):
                node_id = int(path_.name.split("_")[1])
                for sub_path in path_.iterdir():
                    self.process_path(sub_path, node_id)
        self.log2node = dict(sorted(self.log2node.items(), key=lambda x: (x[1], x[0])))


    def yield_log(self, log_id: int, events: set = None, fn: Callable[[dict], bool] = None) -> Generator[dict, None, None]:
        assert log_id in self.logs, f"Log {log_id} not found in results folder."
        for line in self.logs[log_id]:
            if (
                (events is not None and line["event"] in events) or
                (fn is not None and fn(line))
            ):
                yield line


    @lru_cache(maxsize=1)
    def get_validations(self) -> pd.DataFrame:
        data = []
        starts = self.yield_log(0, {"validation_start"})
        ends = self.yield_log(0, {"validation_end"})
        for start, end in zip(starts, ends, strict=True):
            data.append((
                datetime.fromtimestamp(start["timestamp"]),
                datetime.fromtimestamp(end["timestamp"]),
                end["timestamp"] - start["timestamp"]
            ))
        return pd.DataFrame(data, columns=["start", "end", "duration"])
    

    def get_generic(self, event: str, log_id: int = None, cols: list[str] = None) -> pd.DataFrame:
        data = []
        if cols is None:
            cols = []
        logs = self.logs if log_id is None else [log_id]
        for id_ in logs:
            for line in self.yield_log(id_, {event}):
                data.append((
                    self.log2node[id_],
                    id_,
                    datetime.fromtimestamp(line["timestamp"]),
                    *(line[col] for col in cols) 
                ))
        df = pd.DataFrame(data, columns=["nid", "lid", "timestamp", *cols])
        df = df.sort_values(by=["timestamp"])
        return df
    

    @lru_cache(maxsize=1)
    def get_failures(self) -> pd.DataFrame:
        df = self.get_generic("failure")
        return df
    

    @lru_cache(maxsize=1)
    def get_joins(self) -> pd.DataFrame:
        df = self.get_generic("join", 0, ["node_id"])
        df = df.drop(columns=["nid", "lid"])
        df = df.rename(columns={"node_id": "lid"})
        df["nid"] = df["lid"].apply(lambda x: self.log2node[x])
        return df
    

    @lru_cache(maxsize=1)
    def get_exits(self) -> pd.DataFrame:
        df = self.get_generic("leave", 0, ["node_id"])
        df = df.drop(columns=["nid", "lid"])
        df = df.rename(columns={"node_id": "lid"})
        df["nid"] = df["lid"].apply(lambda x: self.log2node[x])
        return df
    

    @lru_cache(maxsize=1)
    def get_new_workers(self) -> pd.DataFrame:
        df = self.get_generic("new_worker", 0, ["node_id"])
        df = df.drop(columns=["nid", "lid"])
        df = df.rename(columns={"node_id": "lid"})
        df["nid"] = df["lid"].apply(lambda x: self.log2node[x])
        return df


    @lru_cache(maxsize=1)
    def get_work_times(self) -> pd.DataFrame:
        data = []
        for log_id in self.logs:
            starts = self.yield_log(log_id, {"working_start"})
            ends = self.yield_log(log_id, {"working_end", "failure"})
            for start, end in zip(starts, ends):
                data.append((
                    self.log2node[log_id],
                    log_id,
                    datetime.fromtimestamp(start["timestamp"]),
                    datetime.fromtimestamp(end["timestamp"]),
                    end["timestamp"] - start["timestamp"],
                ))
        df = pd.DataFrame(data, columns=[ "nid", "lid", "start", "end", "duration"])
        df = df.sort_values(by=["nid", "start"])
        return df
    

    @lru_cache(maxsize=1)
    def get_comms(self) -> pd.DataFrame:
        data = []
        for a1, a2, a3 in [("send", "recv", "receiver"), ("recv", "send", "sender")]:
            for log_id in set(self.logs.keys()) - {0}:
                l1s = self.yield_log(0, None, lambda x: x["event"] == a1 and x[a3] == log_id)
                l2s = self.yield_log(log_id, {a2})
                for l1, l2 in zip(l1s, l2s):
                    t1 = l1["timestamp"]
                    t2 = l2["timestamp"]
                    sender = l1["sender"]
                    receiver = l1["receiver"]
                    if a1 == "send":
                        start = t1
                        end = t2
                    else:
                        start = t2
                        end = t1
                    duration = (end - start) * 1000
                    if duration < 0:
                        raise ValueError(f"Negative duration: {duration} ms")
                    data.append((
                        self.log2node[sender],
                        sender,
                        self.log2node[receiver],
                        receiver,
                        datetime.fromtimestamp(start),
                        datetime.fromtimestamp(end),
                        duration,
                        l1["payload_size"]
                    ))
        df = pd.DataFrame(data, columns=["send_nid", "send_lid", "recv_nid", "recv_lid", "start", "end", "duration (ms)", "payload_size (bytes)"])
        df = df.sort_values(by=["start"])
        return df
    

    @lru_cache(maxsize=1)
    def get_metrics(self) -> pd.DataFrame:
        data = []
        logs = self.yield_log(0, {"epoch"})
        for log in logs:
            log = {**log}
            log.pop("event")
            log.pop("timestamp")
            data.append((
                *log.values(),
            ))
        df = pd.DataFrame(data, columns=[*log.keys()])
        df = df.sort_values(by=["epoch"])
        return df
    

    @lru_cache(maxsize=1)
    def get_comms_per_worker(self) -> pd.DataFrame:
        df = self.get_comms()
        df["worker"] = df.apply(lambda x: max(x["send_nid"], x["recv_nid"]), axis=1)
        df = df.groupby(["worker"]).agg({
            "duration (ms)": "sum",
            "payload_size (bytes)": "sum"
        })
        df = df.reset_index()
        df["payload_size (bytes)"] = df["payload_size (bytes)"] / 1024 / 1024
        df["duration (ms)"] = df["duration (ms)"] / 1000
        df = df.rename(columns={
            "payload_size (bytes)": "payload_size (MB)",
            "duration (ms)": "comm_time (s)"
        })
        df = df.sort_values(by=["worker"])
        return df
    

    @lru_cache(maxsize=1)
    def get_work_time_per_worker(self) -> pd.DataFrame:
        df = self.get_work_times()
        df = df.rename(columns={"nid": "worker"})
        df = df.groupby(["worker"]).agg({
            "duration": "sum",
        })
        df = df.reset_index()
        df = df.rename(columns={
            "duration": "work_time (s)"
        })
        return df
    

    @lru_cache(maxsize=1)
    def get_worker_start_end(self) -> pd.DataFrame:
        data = []
        for log_id in set(self.logs.keys()) - {0}:
            worker_id = self.log2node[log_id]
            start = self.logs[log_id][0]["timestamp"]
            end = self.logs[log_id][-1]["timestamp"]
            data.append((
                worker_id,
                log_id,
                datetime.fromtimestamp(start),
                datetime.fromtimestamp(end),
            ))
        df = pd.DataFrame(data, columns=["nid", "lid", "start", "end"])
        df = df.rename(columns={"nid": "worker"})
        df = df.groupby(["worker"]).agg({
            "start": "min",
            "end": "max",
        })
        df = df.reset_index()
        df["duration"] = df["end"] - df["start"]
        df["duration"] = df["duration"].dt.total_seconds()
        df = df.rename(columns={
            "duration": "total_time (s)"
        })
        df = df.sort_values(by=["worker"])
        return df
    

    @lru_cache(maxsize=1)
    def get_worker_time_status(self) -> pd.DataFrame:
        cpm = self.get_comms_per_worker()
        wtpw = self.get_work_time_per_worker()
        wse = self.get_worker_start_end()
        df = pd.merge(cpm, wtpw, on="worker", how="outer")
        df = pd.merge(df, wse, on="worker", how="outer")
        df["other_time (s)"] = df["total_time (s)"] - df["work_time (s)"] - df["comm_time (s)"]
        df["comm_time% (s)"] = df["comm_time (s)"] / df["total_time (s)"] * 100
        df["work_time% (s)"] = df["work_time (s)"] / df["total_time (s)"] * 100
        df["other_time% (s)"] = df["other_time (s)"] / df["total_time (s)"] * 100
        df = df.drop(columns=["start", "end"])
        return df
    

    def add_to_timeline(self, fig: go.Figure, df: pd.DataFrame, x: str, y: str, color: str, title: str) -> None:
        df[y] = df[y].astype(str)
        fig.add_trace(go.Scatter(
            x=df[x],
            y=df[y],
            mode="markers",
            name=title,
            marker=dict(
                color=color,
                size=10,
                line=dict(color="black", width=2)
            ), 
        ))
    

    def plot_timeline(self) -> None:
        worktimes = self.get_work_times()
        failures = self.get_failures()
        joins = self.get_new_workers()
        worktimes = worktimes.rename(columns={"nid": "worker"})
        worktimes = worktimes.sort_values(by=["worker"], ascending=False)
        worktimes["worker"] = worktimes["worker"].astype(str)
        fig = px.timeline(
            worktimes,
            x_start="start", 
            x_end="end", 
            y="worker", 
            title="Worker timeline", 
            color="worker", 
            color_discrete_sequence=px.colors.qualitative.Safe,
            labels={"worker": "Legend"}
        )
        for trace in fig.data:
            trace.showlegend = False
        self.add_to_timeline(fig, failures, "timestamp", "nid", "red", "Failures")
        self.add_to_timeline(fig, joins, "timestamp", "nid", "green", "Joins")
        fig.update_yaxes(title="Workers")
        fig.update_xaxes(title="Time", showticklabels=False)
        start = worktimes["start"].min() 
        end = worktimes["end"].max()
        diff = end - start
        fig.update_xaxes(range=[start - diff * 0.05, end + diff * 0.05])
        fig.show()


    def plot_training(self) -> None:
        data = self.get_metrics()
        metrics = data.columns[-3:]
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Loss over epochs", "Metrics over epochs")
        )
        fig1 = px.line(data, x="epoch", y="loss", labels={"epoch": "Epoch", "loss": "Loss"})
        for trace in fig1.data:
            fig.add_trace(trace, row=1, col=1)
        fig2 = px.line(data, x="epoch", y=metrics, labels={"epoch": "Epoch"})
        for trace in fig2.data:
            fig.add_trace(trace, row=1, col=2)
        fig.update_layout(title_text="Training Overview", showlegend=True)
        fig.show()
        

    def plot_times(self) -> None:
        df = self.get_worker_time_status()
        df_melted = df.melt(
            id_vars="worker", 
            value_vars=["comm_time% (s)", "work_time% (s)", "other_time% (s)"],
            var_name="Time Type", value_name="Percentage"
        )
        label_map = {
            "comm_time% (s)": "Communication",
            "work_time% (s)": "Working",
            "other_time% (s)": "Other"
        }
        df_melted["Time Type"] = df_melted["Time Type"].map(label_map)
        fig = px.bar(
            df_melted,
            x="worker",
            y="Percentage",
            color="Time Type",
            title="Worker Time Status",
            labels={"worker": "Worker", "Percentage": "Time (%)"},
            color_discrete_sequence=px.colors.qualitative.Safe
        )
        fig.update_layout(barmode="stack")
        fig.show()