import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

EVENTS = Path("data/processed/canonical_events_v1.jsonl")
QC = Path("results/statistics/canonical_extraction_qc.csv")
OUT_SUMMARY = Path("results/statistics/canonical_qc_summary.csv")
OUT_UNKNOWNS = Path("results/statistics/canonical_unknown_structures.csv")
events = []
with EVENTS.open() as f:
    for line in f:
        if line.strip():
            events.append(json.loads(line))
qc_rows = list(csv.DictReader(QC.open()))
event_ids = [e["event_id"] for e in events]
duplicate_event_ids = (len(event_ids) - len(set(event_ids)))
by_traj = defaultdict(list)
for e in events:
    by_traj[e["trajectory_id"]].append(e)
bad_indexes = 0
negative_relative_times = 0
for traj, xs in by_traj.items():
    indexes = sorted(e["canonical_event_index"] for e in xs)
    expected = list(range(len(xs)))
    if indexes != expected:
        bad_indexes += 1
    for e in xs:
        t = e.get("relative_time_sec")
        if (
            t is not None
            and float(t) < -1e-9
        ):
            negative_relative_times += 1

tool_calls = [e for e in events if e["event_type"] == "tool_call"]
tool_results = [e for e in events if e["event_type"] in {"tool_result", "error"} and e.get("tool_call_id")]
linked_results = [e for e in tool_results if e.get("parent_event_id")]
call_ids = {e.get("tool_call_id") for e in tool_calls if e.get("tool_call_id")}
result_call_ids = {e.get("tool_call_id") for e in tool_results if e.get("tool_call_id")}
unmatched_result_ids = (result_call_ids - call_ids)
read_failures = sum(r["read_failed"] == "True" for r in qc_rows)
empty_transcripts = sum(r["empty_transcript"] == "True" for r in qc_rows)
non_json_lines = sum(int(r["n_non_json_lines"]) for r in qc_rows)
raw_records = sum(int(r["n_json_records"]) for r in qc_rows)
unknowns = Counter()
for r in qc_rows:
    s = r["unknown_structures"]
    if not s:
        continue
    for part in s.split("|"):
        if not part:
            continue
        try:
            label, n = part.rsplit(":", 1)
            unknowns[label] += int(n)
        except ValueError:
            unknowns[part] += 1
OUT_UNKNOWNS.parent.mkdir(parents=True, exist_ok=True)
with OUT_UNKNOWNS.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "unknown_structure",
        "count",
        "fraction_of_events",
    ])
    for label, n in unknowns.most_common():
        w.writerow([
            label,
            n,
            n / len(events),
        ])
summary = [
    ("canonical_events", len(events)),
    ("provider_trajectories", len(by_traj)),
    ("transcript_files", len(qc_rows)),
    ("raw_json_records", raw_records),
    ("non_json_lines", non_json_lines),
    ("read_failures", read_failures),
    ("empty_transcripts", empty_transcripts),
    ("duplicate_event_ids", duplicate_event_ids),
    ("trajectories_bad_event_index", bad_indexes),
    ("negative_relative_times", negative_relative_times),
    ("tool_calls", len(tool_calls)),
    ("tool_results_or_linked_errors", len(tool_results)),
    ("linked_tool_results", len(linked_results)),
    ("tool_result_link_rate", (len(linked_results) / len(tool_results) if tool_results else None)),
    ("unmatched_tool_call_ids", len(unmatched_result_ids)),
    ("unknown_structure_occurrences", sum(unknowns.values())),
    ("unknown_fraction_of_events", sum(unknowns.values()) / len(events)),
]
with OUT_SUMMARY.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["metric", "value"])
    w.writerows(summary)
print("\nCANONICAL QC")
print("---------------")
for metric, value in summary:
    print(f"{metric:35s} {value}")
print("\nTOP UNKNOWN STRUCTURES")
print("-------------------------")
for label, n in unknowns.most_common(20):
    print(f"{label:45s} {n:6d}")
print("\nWrote:")
print(OUT_SUMMARY)
print(OUT_UNKNOWNS)