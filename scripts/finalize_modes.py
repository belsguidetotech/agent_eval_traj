from pathlib import Path
import subprocess
import csv
from datetime import datetime, timezone
from collections import Counter

TREE_ROOT = Path("data/cache/repo_metadata")

SIGNALS = "results/reconnaissance/all_repo_mode_signals.csv"
RUN_META = "results/reconnaissance/run_metadata.csv"

OUT = "results/reconnaissance/final_repo_modes.csv"

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


def tree(repo):
    p = subprocess.run(
        [
            "git", "-C", str(repo),
            "ls-tree", "-r",
            "--name-only", "HEAD"
        ],
        capture_output=True,
        text=True
    )

    if p.returncode != 0:
        return []

    return [
        x.strip()
        for x in p.stdout.splitlines()
        if x.strip()
    ]


signals = {
    r["repo_name"]: r
    for r in csv.DictReader(open(SIGNALS))
}

runmeta = {
    r["repo_name"]: r
    for r in csv.DictReader(open(RUN_META))
}

rows = []


for name, sig in signals.items():

    repo = TREE_ROOT / name
    paths = tree(repo)

    low = [p.lower() for p in paths]

    # ==================================================
    # STRICT HITL runtime markers
    # ==================================================

    hitl_paths = [
        p for p in low
        if (
            p.startswith(".neurico/hitl/")
            or p.startswith("logs/hitl/")
            or "/hitl-runtime/" in p
        )
    ]

    has_hitl = bool(hitl_paths)

    # ==================================================
    # STRICT AutoResearch runtime markers
    #
    # IMPORTANT:
    # Do NOT match arbitrary "autoresearch" papers/code.
    # ==================================================

    auto_paths = [
        p for p in low
        if (
            p.startswith("logs/experiment-autoresearch/")
            or "/experiment-autoresearch/" in p
            or p == "logs/experiment-autoresearch/whiteboard.json"
        )
    ]

    has_autoresearch = bool(auto_paths)

    # ==================================================
    # Ordinary NeuriCo pipeline
    # ==================================================

    has_pipeline = (
        ".neurico/pipeline_state.json" in low
    )

    has_pipeline_results = (
        ".neurico/pipeline_results.json" in low
    )

    # ==================================================
    # Actual execution timestamp
    # ==================================================

    rm = runmeta.get(name, {})

    run_time = parse_dt(
        rm.get("run_created_at")
    )

    repo_created = parse_dt(
        rm.get("repo_created_at")
    )

    # ==================================================
    # Capability era
    # ==================================================

    if run_time:

        temporal_source = "run_created_at"
        t = run_time

    else:

        temporal_source = "none"
        t = None


    if t is None:
        era = "unknown"

    elif t < AR_START:
        era = "pre_autoresearch"

    elif t < HITL_START:
        era = "autoresearch_available"

    else:
        era = "hitl_available"

    # ==================================================
    # Classification
    # ==================================================

    if has_hitl:

        mode = "hitl"
        confidence = "high"
        source = "runtime_hitl_artifact"

    elif has_autoresearch:

        mode = "autoresearch"
        confidence = "high"
        source = "runtime_autoresearch_artifact"

    elif (
        sig["repo_status"] == "executed"
        and era == "pre_autoresearch"
    ):

        mode = "standard"
        confidence = "high"
        source = "run_timestamp_pre_autoresearch"

    elif (
        sig["repo_status"] == "executed"
        and has_pipeline
        and not has_hitl
        and not has_autoresearch
    ):

        # Standard-looking run after newer modes existed.
        # Runtime evidence strongly suggests ordinary pipeline,
        # but absence alone is weaker than historical impossibility.

        mode = "standard"
        confidence = "medium"
        source = "ordinary_pipeline_no_alt_runtime"

    else:

        mode = "unknown"
        confidence = "low"
        source = "insufficient_runtime_evidence"

    rows.append({
        "repo_name": name,
        "repo_status": sig["repo_status"],
        "provider": sig["provider"],

        "run_created_at": rm.get(
            "run_created_at", ""
        ),

        "repo_created_at": rm.get(
            "repo_created_at", ""
        ),

        "capability_era": era,
        "temporal_source": temporal_source,

        "has_pipeline_state": has_pipeline,
        "has_pipeline_results": has_pipeline_results,

        "has_autoresearch_runtime": has_autoresearch,
        "has_hitl_runtime": has_hitl,

        "mode": mode,
        "confidence": confidence,
        "mode_source": source,

        "autoresearch_examples":
            "|".join(auto_paths[:5]),

        "hitl_examples":
            "|".join(hitl_paths[:5]),
    })


with open(OUT, "w", newline="") as f:

    writer = csv.DictWriter(
        f,
        fieldnames=rows[0].keys()
    )

    writer.writeheader()
    writer.writerows(rows)


print("\nFINAL MODES")
print("-----------")

for k, v in Counter(
    r["mode"] for r in rows
).most_common():

    print(f"{k:20s} {v:5d}")


print("\nMODE SOURCE")
print("-----------")

for k, v in Counter(
    r["mode_source"] for r in rows
).most_common():

    print(f"{k:35s} {v:5d}")


print("\nEXECUTED UNKNOWN")
print("----------------")

unknown = [
    r for r in rows
    if (
        r["repo_status"] == "executed"
        and r["mode"] == "unknown"
    )
]

print(len(unknown))

for r in unknown:
    print(
        r["run_created_at"],
        r["repo_name"],
        r["capability_era"]
    )


print("\nAUTORESEARCH")
print("------------")

auto = [
    r for r in rows
    if r["mode"] == "autoresearch"
]

print(len(auto))

for r in auto:
    print(
        r["run_created_at"],
        r["repo_name"],
        r["autoresearch_examples"]
    )


print("\nHITL")
print("----")

hitl = [
    r for r in rows
    if r["mode"] == "hitl"
]

print(len(hitl))

for r in hitl:
    print(
        r["run_created_at"],
        r["repo_name"],
        r["hitl_examples"]
    )

print("\nWrote:", OUT)
