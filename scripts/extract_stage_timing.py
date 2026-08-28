from pathlib import Path
import subprocess
import csv
import json
from datetime import datetime, timezone
from collections import Counter

ROOT = Path("data/cache/repo_metadata")
CATALOG = Path("results/statistics/trajectory_catalog.csv")

RUN_OUT = Path("results/statistics/run_summary.csv")
STAGE_OUT = Path("results/statistics/stage_summary.csv")


def git_show(repo, path):
    p = subprocess.run(
        [
            "git", "-C", str(repo),
            "show", f"HEAD:{path}"
        ],
        capture_output=True,
        text=True,
    )

    if p.returncode != 0:
        return None

    return p.stdout


def parse_dt(x):
    if not x:
        return None

    try:
        d = datetime.fromisoformat(
            str(x).replace("Z", "+00:00")
        )

        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)

        return d

    except Exception:
        return None


def duration_seconds(start, end):
    a = parse_dt(start)
    b = parse_dt(end)

    if not a or not b:
        return None

    return (b - a).total_seconds()


catalog = list(csv.DictReader(CATALOG.open()))

included = [
    r for r in catalog
    if r["include_in_analysis"] == "True"
]

run_rows = []
stage_rows = []


for idx, meta in enumerate(included, 1):

    name = meta["repo_name"]
    repo = ROOT / name

    raw = git_show(
        repo,
        ".neurico/pipeline_state.json"
    )

    if not raw:
        run_rows.append({
            "repo_name": name,
            "provider": meta["provider"],
            "has_pipeline_state": False,
            "run_started_at": "",
            "run_completed_at": "",
            "run_duration_sec": "",
            "pipeline_completed": "",
            "n_stages": 0,
            "stage_sequence": "",
        })
        continue

    try:
        state = json.loads(raw)
    except Exception:
        continue

    stages = state.get("stages", {}) or {}

    run_start = state.get("created_at")
    run_end = state.get("completed_at")

    # If completed_at is absent, infer from the
    # latest completed stage when possible.
    stage_end_times = []

    for stage_name, stage in stages.items():

        if not isinstance(stage, dict):
            continue

        start = (
            stage.get("started_at")
            or stage.get("start_time")
            or stage.get("created_at")
        )

        end = (
            stage.get("completed_at")
            or stage.get("end_time")
            or stage.get("finished_at")
        )

        if end:
            stage_end_times.append(end)

        success = stage.get("success")

        if success is None:
            success = stage.get("completed")

        return_code = (
            stage.get("return_code")
            or stage.get("exit_code")
        )

        elapsed = stage.get("elapsed_seconds")

        if elapsed is None:
            elapsed = stage.get("elapsed")

        calculated_duration = duration_seconds(
            start,
            end
        )

        # Prefer explicit elapsed if numeric.
        if isinstance(elapsed, (int, float)):
            duration = elapsed
            duration_source = "explicit_elapsed"

        elif calculated_duration is not None:
            duration = calculated_duration
            duration_source = "timestamps"

        else:
            duration = ""
            duration_source = ""

        stage_rows.append({
            "repo_name": name,
            "provider": meta["provider"],
            "stage_name": stage_name,

            "stage_started_at": start or "",
            "stage_completed_at": end or "",

            "stage_duration_sec": duration,
            "duration_source": duration_source,

            "success": success,
            "return_code": return_code or "",

            "has_error": bool(
                stage.get("error")
                or (
                    return_code not in (
                        None, "", 0, "0"
                    )
                )
            ),
        })


    if not run_end and stage_end_times:

        parsed = [
            (parse_dt(t), t)
            for t in stage_end_times
            if parse_dt(t)
        ]

        if parsed:
            parsed.sort()
            run_end = parsed[-1][1]


    run_rows.append({
        "repo_name": name,
        "provider": meta["provider"],

        "has_pipeline_state": True,

        "run_started_at": run_start or "",
        "run_completed_at": run_end or "",

        "run_duration_sec":
            duration_seconds(
                run_start,
                run_end
            ) or "",

        "pipeline_completed":
            state.get("completed"),

        "n_stages": len(stages),

        "stage_sequence":
            "|".join(stages.keys()),
    })


RUN_OUT.parent.mkdir(
    parents=True,
    exist_ok=True
)


with RUN_OUT.open("w", newline="") as f:

    w = csv.DictWriter(
        f,
        fieldnames=run_rows[0].keys()
    )

    w.writeheader()
    w.writerows(run_rows)


with STAGE_OUT.open("w", newline="") as f:

    w = csv.DictWriter(
        f,
        fieldnames=stage_rows[0].keys()
    )

    w.writeheader()
    w.writerows(stage_rows)


print("\nRUNS")
print("----")
print("Total included:", len(included))
print(
    "With pipeline state:",
    sum(r["has_pipeline_state"] for r in run_rows)
)
print(
    "Without pipeline state:",
    sum(not r["has_pipeline_state"] for r in run_rows)
)


print("\nSTAGE SEQUENCES")
print("---------------")

for k, v in Counter(
    r["stage_sequence"]
    for r in run_rows
    if r["stage_sequence"]
).most_common():

    print(f"{v:5d}  {k}")


print("\nSTAGE COUNTS")
print("------------")

for k, v in Counter(
    r["stage_name"]
    for r in stage_rows
).most_common():

    print(f"{v:5d}  {k}")


print("\nPIPELINE COMPLETION")
print("-------------------")

for k, v in Counter(
    str(r["pipeline_completed"])
    for r in run_rows
    if r["has_pipeline_state"]
).most_common():

    print(f"{v:5d}  {k}")


print("\nWrote:")
print(RUN_OUT)
print(STAGE_OUT)
