import csv
from pathlib import Path
from collections import Counter

FINAL = Path(
    "results/reconnaissance/final_repo_modes.csv"
)

LEGACY = Path(
    "results/reconnaissance/legacy_unknown_audit.csv"
)

OUT = Path(
    "results/statistics/trajectory_catalog.csv"
)

final_rows = list(csv.DictReader(FINAL.open()))
legacy_rows = list(csv.DictReader(LEGACY.open()))

legacy = {
    r["repo_name"]: r
    for r in legacy_rows
}

rows = []

for r in final_rows:

    name = r["repo_name"]
    status = r["repo_status"]

    mode = r["mode"]
    confidence = r["confidence"]
    source = r["mode_source"]

    # Resolve legacy executed repositories.
    if (
        mode == "unknown"
        and name in legacy
        and legacy[name]["proposed_mode"] == "standard"
    ):
        mode = "standard"
        confidence = "high"
        source = "head_commit_pre_autoresearch"

    # Determine whether this is an analyzable trajectory.
    is_trajectory = (
        status == "executed"
    )

    include = is_trajectory

    if include:
        exclusion_reason = ""
    elif status == "initialized_only":
        exclusion_reason = "initialized_only_no_execution"
    elif status == "empty":
        exclusion_reason = "empty_repository"
    else:
        exclusion_reason = "no_analyzable_execution"

    rows.append({
        "repo_name": name,
        "repo_status": status,

        "is_trajectory": is_trajectory,
        "include_in_analysis": include,
        "exclusion_reason": exclusion_reason,

        "mode": mode if include else "",
        "mode_confidence": confidence if include else "",
        "mode_source": source if include else "",

        "provider": r["provider"],

        "repo_created_at": r["repo_created_at"],
        "run_created_at": r["run_created_at"],

        "capability_era": r["capability_era"],

        "has_pipeline_state": r["has_pipeline_state"],
        "has_pipeline_results": r["has_pipeline_results"],

        "has_autoresearch_runtime":
            r["has_autoresearch_runtime"],

        "has_hitl_runtime":
            r["has_hitl_runtime"],
    })


OUT.parent.mkdir(
    parents=True,
    exist_ok=True
)

with OUT.open("w", newline="") as f:

    writer = csv.DictWriter(
        f,
        fieldnames=rows[0].keys()
    )

    writer.writeheader()
    writer.writerows(rows)


print("\nTOTAL REPOSITORIES:", len(rows))

print(
    "ANALYZABLE TRAJECTORIES:",
    sum(
        r["include_in_analysis"]
        for r in rows
    )
)

print("\nREPO STATUS")
print("-----------")

for k, v in Counter(
    r["repo_status"]
    for r in rows
).most_common():

    print(f"{k:25s} {v:5d}")


print("\nTRAJECTORY MODES")
print("----------------")

included = [
    r for r in rows
    if r["include_in_analysis"]
]

for k, v in Counter(
    r["mode"]
    for r in included
).most_common():

    print(f"{k:25s} {v:5d}")


print("\nMODE SOURCES")
print("------------")

for k, v in Counter(
    r["mode_source"]
    for r in included
).most_common():

    print(f"{k:35s} {v:5d}")


print("\nWrote:", OUT)
