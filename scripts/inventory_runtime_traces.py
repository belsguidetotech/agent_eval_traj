from pathlib import Path
import subprocess
import csv
from collections import Counter

ROOT = Path("data/cache/repo_metadata")
CATALOG = Path("results/statistics/trajectory_catalog.csv")
OUT = Path("results/reconnaissance/runtime_trace_inventory.csv")


def git_tree(repo):
    p = subprocess.run(
        [
            "git", "-C", str(repo),
            "ls-tree", "-r", "--name-only", "HEAD"
        ],
        capture_output=True,
        text=True,
    )

    if p.returncode != 0:
        return []

    return [
        x.strip()
        for x in p.stdout.splitlines()
        if x.strip()
    ]


catalog = list(csv.DictReader(CATALOG.open()))

included = [
    r for r in catalog
    if r["include_in_analysis"] == "True"
]

rows = []

for i, meta in enumerate(included, 1):

    name = meta["repo_name"]
    paths = git_tree(ROOT / name)

    runtime_transcripts = [
        p for p in paths
        if (
            p.lower().startswith("logs/")
            and Path(p).name.lower().endswith("_transcript.jsonl")
        )
    ]

    resource_transcripts = [
        p for p in runtime_transcripts
        if "resource_finder" in Path(p).name.lower()
    ]

    execution_transcripts = [
        p for p in runtime_transcripts
        if (
            "execution" in Path(p).name.lower()
            or "experiment" in Path(p).name.lower()
        )
    ]

    other_runtime_transcripts = [
        p for p in runtime_transcripts
        if p not in (
            resource_transcripts
            + execution_transcripts
        )
    ]

    runtime_logs = [
        p for p in paths
        if p.lower().startswith("logs/")
    ]

    if runtime_transcripts:
        family = "runtime_transcript"
    elif runtime_logs:
        family = "runtime_logs_no_transcript"
    else:
        family = "no_committed_runtime_trace"

    rows.append({
        "repo_name": name,
        "provider": meta["provider"],
        "trace_family": family,

        "n_runtime_transcripts":
            len(runtime_transcripts),

        "n_resource_transcripts":
            len(resource_transcripts),

        "n_execution_transcripts":
            len(execution_transcripts),

        "n_other_runtime_transcripts":
            len(other_runtime_transcripts),

        "n_log_files":
            len(runtime_logs),

        "runtime_transcript_examples":
            "|".join(runtime_transcripts[:10]),

        "other_transcript_examples":
            "|".join(other_runtime_transcripts[:10]),
    })

    if i % 50 == 0:
        print(f"Processed {i}/{len(included)}")


OUT.parent.mkdir(parents=True, exist_ok=True)

with OUT.open("w", newline="") as f:
    w = csv.DictWriter(
        f,
        fieldnames=rows[0].keys()
    )
    w.writeheader()
    w.writerows(rows)


print("\nTRACE FAMILY")
print("------------")

for k, v in Counter(
    r["trace_family"] for r in rows
).most_common():
    print(f"{k:30s} {v:5d}")


print("\nRUNTIME TRANSCRIPTS PER REPO")
print("----------------------------")

for k, v in sorted(
    Counter(
        r["n_runtime_transcripts"]
        for r in rows
    ).items()
):
    print(f"{k:3d}: {v:4d} repos")


print("\nRESOURCE / EXECUTION PATTERNS")
print("-----------------------------")

patterns = Counter(
    (
        r["n_resource_transcripts"],
        r["n_execution_transcripts"],
        r["n_other_runtime_transcripts"],
    )
    for r in rows
)

for pattern, n in patterns.most_common():
    print(
        f"{n:4d} repos  "
        f"resource={pattern[0]} "
        f"execution={pattern[1]} "
        f"other={pattern[2]}"
    )


print("\nEXCEPTIONAL REPOS")
print("-----------------")

for r in rows:

    n = r["n_runtime_transcripts"]

    # Normal successful two-stage pattern is expected
    # to be resource=1, execution=1.
    if n > 0 and not (
        r["n_resource_transcripts"] == 1
        and r["n_execution_transcripts"] == 1
        and r["n_other_runtime_transcripts"] == 0
    ):
        print(
            r["repo_name"],
            "total=", n,
            "resource=", r["n_resource_transcripts"],
            "execution=", r["n_execution_transcripts"],
            "other=", r["n_other_runtime_transcripts"],
        )
        print(
            " ",
            r["runtime_transcript_examples"]
        )


print("\nWrote:", OUT)