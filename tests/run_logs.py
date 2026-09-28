import json
from pathlib import Path

MASTER_EVENTS = [
    {"event": "start", "timestamp": 100.0},
    {"event": "encode", "time": 0.25, "timestamp": 100.25},
    {"event": "send", "sender": 0, "receiver": 1, "payload_size": 10, "timestamp": 100.25},
    {"event": "send", "sender": 0, "receiver": 3, "payload_size": 10, "timestamp": 100.25},
    {"event": "recv", "sender": 1, "receiver": 0, "payload_size": 20, "timestamp": 103.5},
    {"event": "decode", "time": 0.25, "timestamp": 103.5},
    {"event": "recv", "sender": 3, "receiver": 0, "payload_size": 20, "timestamp": 104.0},
    {"event": "validation_start", "timestamp": 104.0},
    {"event": "validation_end", "timestamp": 105.0},
    {"event": "send", "sender": 0, "receiver": 4, "payload_size": 10, "timestamp": 105.0},
    {"event": "recv", "sender": 4, "receiver": 0, "payload_size": 20, "timestamp": 109.0},
    {"event": "end", "timestamp": 110.0},
]

WORKER_EVENTS = {
    ("worker_1", 1): [
        {"event": "recv", "sender": 0, "receiver": 1, "payload_size": 10, "timestamp": 100.5},
        {"event": "decode", "time": 0.25, "timestamp": 100.75},
        {"event": "working_start", "timestamp": 100.75},
        {"event": "working_end", "timestamp": 102.75},
        {"event": "encode", "time": 0.25, "timestamp": 103.0},
        {"event": "send", "sender": 1, "receiver": 0, "payload_size": 20, "timestamp": 103.0},
        {"event": "working_start", "timestamp": 111.0},
        {"event": "working_end", "timestamp": 113.0},
    ],
    ("worker_2", 3): [
        {"event": "recv", "sender": 0, "receiver": 3, "payload_size": 10, "timestamp": 99.5},
        {"event": "working_start", "timestamp": 99.5},
        {"event": "working_end", "timestamp": 101.5},
        {"event": "send", "sender": 3, "receiver": 0, "payload_size": 20, "timestamp": 103.5},
    ],
    ("worker_2", 4): [
        {"event": "recv", "sender": 0, "receiver": 4, "payload_size": 10, "timestamp": 105.25},
        {"event": "working_start", "timestamp": 105.25},
        {"event": "working_end", "timestamp": 108.25},
        {"event": "send", "sender": 4, "receiver": 0, "payload_size": 20, "timestamp": 108.5},
    ],
}


def golden_logs() -> tuple[dict[int, list[dict]], dict[int, int]]:
    logs = {0: [dict(e) for e in MASTER_EVENTS]}
    log2node = {0: 0}
    for (folder, log_id), events in WORKER_EVENTS.items():
        logs[log_id] = [dict(e) for e in events]
        log2node[log_id] = int(folder.split("_")[1])
    return logs, log2node


def write_run_logs(folder: Path, master_events: list[dict] | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    events = MASTER_EVENTS if master_events is None else master_events
    (folder / "log_0.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    for (worker, log_id), worker_events in WORKER_EVENTS.items():
        path = folder / worker / f"log_{log_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(e) for e in worker_events) + "\n")
    return folder
