"""Event pairing over FlexFL run logs, shared by Results and scripts/assemble_meta_dataset.py.

Stdlib only: the assembler imports this module under a Python that has no pandas.
"""

WORK_EVENTS = ("working_start", "working_end", "failure")


def work_intervals(logs: dict[int, list[dict]], log2node: dict[int, int]) -> list[tuple[int, int, float, float]]:
    rows = []
    for log_id in logs:
        starts = [e for e in logs[log_id] if e["event"] == "working_start"]
        ends = [e for e in logs[log_id] if e["event"] in ("working_end", "failure")]
        for start, end in zip(starts, ends):
            rows.append((log2node[log_id], log_id, start["timestamp"], end["timestamp"]))
    return rows


def comm_pairs(
    logs: dict[int, list[dict]], log2node: dict[int, int]
) -> tuple[list[tuple[int, int, int, int, float, float, float, int]], int, float, int]:
    rows = []
    skew_count = 0
    max_skew = 0.0
    unmatched = 0
    for a1, a2, a3 in [("send", "recv", "receiver"), ("recv", "send", "sender")]:
        for log_id in set(logs.keys()) - {0}:
            l1s = [e for e in logs[0] if e["event"] == a1 and e[a3] == log_id]
            l2s = [e for e in logs[log_id] if e["event"] == a2]
            if len(l1s) != len(l2s):
                unmatched += abs(len(l1s) - len(l2s))
            for l1, l2 in zip(l1s, l2s):
                t1 = l1["timestamp"]
                t2 = l2["timestamp"]
                start, end = (t1, t2) if a1 == "send" else (t2, t1)
                duration = (end - start) * 1000
                if duration < 0:
                    skew_count += 1
                    max_skew = max(max_skew, -duration)
                    duration = 0.0
                rows.append((
                    log2node[l1["sender"]], l1["sender"], log2node[l1["receiver"]], l1["receiver"],
                    start, end, duration, l1["payload_size"],
                ))
    return rows, skew_count, max_skew, unmatched


def serialization_totals(logs: dict[int, list[dict]], log2node: dict[int, int]) -> list[tuple[int, float]]:
    return [
        (log2node[log_id], sum(e["time"] for e in logs[log_id] if e["event"] in ("encode", "decode")))
        for log_id in set(logs.keys()) - {0}
    ]


def _overlap(start: float, end: float, t0: float, t1: float) -> float:
    return max(0.0, min(end, t1) - max(start, t0))


def decomposition(logs: dict[int, list[dict]], log2node: dict[int, int], t0: float, t1: float) -> dict[str, float | int]:
    workers = {log_id: events for log_id, events in logs.items() if log_id != 0}
    nodes = {log2node[log_id] for log_id in workers}
    compute = dict.fromkeys(nodes, 0.0)
    in_window = 0
    for nid, _, start, end in work_intervals(workers, log2node):
        seconds = _overlap(start, end, t0, t1)
        compute[nid] += seconds
        in_window += seconds > 0
    comm = dict.fromkeys(nodes, 0.0)
    pairs, skew_count, _, unmatched = comm_pairs(logs, log2node)
    for send_nid, _, recv_nid, _, start, end, _, _ in pairs:
        comm[max(send_nid, recv_nid)] += _overlap(start, end, t0, t1)
    serial = sum(
        _overlap(e["timestamp"] - e["time"], e["timestamp"], t0, t1)
        for events in logs.values()
        for e in events
        if e["event"] in ("encode", "decode")
    )
    validation_starts = [e for e in logs[0] if e["event"] == "validation_start"]
    validation_ends = [e for e in logs[0] if e["event"] == "validation_end"]
    validation = sum(
        _overlap(s["timestamp"], e["timestamp"], t0, t1) for s, e in zip(validation_starts, validation_ends)
    )
    return {
        "compute_time_total_s": sum(compute.values()),
        "compute_time_max_s": max(compute.values(), default=0.0),
        "comm_time_total_s": sum(comm.values()),
        "comm_time_max_s": max(comm.values(), default=0.0),
        "serial_time_total_s": serial,
        "validation_time_s": validation,
        "comm_skew_clamped": skew_count,
        "n_work_intervals_in_window": in_window,
        "n_work_events_in_window": sum(
            1 for events in workers.values() for e in events
            if e["event"] in WORK_EVENTS and t0 <= e["timestamp"] <= t1
        ),
        "n_unmatched_comms": unmatched,
        "n_orphan_comms": sum(
            1 for e in logs[0]
            if (e["event"] == "send" and e["receiver"] not in logs) or (e["event"] == "recv" and e["sender"] not in logs)
        ),
        "n_unclosed_work_logs": sum(
            1 for events in workers.values()
            if sum(e["event"] == "working_start" for e in events)
            != sum(e["event"] in ("working_end", "failure") for e in events)
        ),
        "n_unmatched_validations": abs(len(validation_starts) - len(validation_ends)),
    }
