from pathlib import Path
import subprocess
import csv
from datetime import datetime, timezone
from collections import Counter

ROOT = Path("data/cache/repo_metadata")
SRC = Path("results/reconnaissance/final_repo_modes.csv")
OUT = Path("results/reconnaissance/legacy_unknown_audit.csv")

AR_START = datetime.fromisoformat(
    "2026-06-13T01:33:04+00:00"
)

HITL_START = datetime.fromisoformat(
    "2026-07-14T07:19:30+00:00"
)


def parse_dt(x):
    if not x:
        return None

    d = datetime.fromisoformat(
        x.replace("Z", "+00:00")
    )

    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)

    return d


def git_head_time(repo):
    p = subprocess.run(
        [
            "git", "-C", str(repo),
            "show", "-s",
            "--format=%cI",
            "HEAD"
        ],
        capture_output=True,
        text=True,
    )

    if p.returncode != 0:
        return None

    return p.stdout.strip()


def git_tree(repo):
    p = subprocess.run(
        [
            "git", "-C", str(repo),
            "ls-tree", "-r",
            "--name-only", "HEAD"
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


rows = list(csv.DictReader(open(SRC)))

audit = []

for r in rows:

    if not (
        r["repo_status"] == "executed"
        and r["mode"] == "unknown"
    ):
        continue

    name = r["repo_name"]
    repo = ROOT / name

    head_raw = git_head_time(repo)
    head_time = parse_dt(head_raw)

    paths = git_tree(repo)
    low = [p.lower() for p in paths]

    # Old Standard-style artifacts
    has_resource_prompt = any(
        p.endswith("resource_finder_prompt.txt")
        for p in low
    )

    has_research_prompt = any(
        p.endswith("research_prompt.txt")
        for p in low
    )

    has_transcript = any(
        "transcript" in p
        for p in low
    )

    has_report = (
        "report.md" in low
    )

    has_state_md = (
        "state.md" in low
    )

    # Strict newer-mode evidence
    has_autoresearch = any(
        p.startswith("logs/experiment-autoresearch/")
        or "/experiment-autoresearch/" in p
        for p in low
    )

    has_hitl = any(
        p.startswith(".neurico/hitl/")
        or p.startswith("logs/hitl/")
        for p in low
    )

    if head_time is None:
        era = "unknown"

    elif head_time < AR_START:
        era = "pre_autoresearch"

    elif head_time < HITL_START:
        era = "autoresearch_available"

    else:
        era = "hitl_available"

    if (
        head_time
        and head_time < AR_START
        and not has_autoresearch
        and not has_hitl
    ):
        proposed_mode = "standard"
        confidence = "high"
        source = "head_commit_pre_autoresearch"

    else:
        proposed_mode = "unknown"
        confidence = "low"
        source = "requires_manual_or_format_check"

    audit.append({
        "repo_name": name,
        "head_commit_time": head_raw or "",
        "head_era": era,

        "has_resource_prompt": has_resource_prompt,
        "has_research_prompt": has_research_prompt,
        "has_transcript": has_transcript,
        "has_report": has_report,
        "has_state_md": has_state_md,

        "has_autoresearch_runtime": has_autoresearch,
        "has_hitl_runtime": has_hitl,

        "proposed_mode": proposed_mode,
        "confidence": confidence,
        "source": source,
    })


with OUT.open("w", newline="") as f:
    w = csv.DictWriter(
        f,
        fieldnames=audit[0].keys()
    )
    w.writeheader()
    w.writerows(audit)


print("\nEXECUTED UNKNOWNS:", len(audit))

print("\nHEAD ERA")
print("--------")

for k, v in Counter(
    r["head_era"] for r in audit
).most_common():

    print(f"{k:25s} {v:5d}")


print("\nPROPOSED CLASSIFICATION")
print("-----------------------")

for k, v in Counter(
    r["proposed_mode"] for r in audit
).most_common():

    print(f"{k:25s} {v:5d}")


remaining = [
    r for r in audit
    if r["proposed_mode"] == "unknown"
]

print("\nSTILL UNRESOLVED:", len(remaining))

for r in remaining:
    print(
        r["head_commit_time"],
        r["repo_name"],
        r["head_era"],
        "transcript=" + str(r["has_transcript"]),
        "report=" + str(r["has_report"]),
        "state=" + str(r["has_state_md"]),
    )


print("\nWrote:", OUT)
