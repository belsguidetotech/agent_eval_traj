import csv
import json
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict

SIGNALS = Path(
    "results/reconnaissance/all_repo_mode_signals.csv"
)
MANIFEST = Path(
    "manifests/hypogenic_repos.json"
)
OUT = Path(
    "results/reconnaissance/all_repo_modes_temporal.csv"
)

# --------------------------------------------------
# Historical capability boundaries from NeuriCo
# origin/main git history.
#
# AutoResearch:
# fee8d1e 2026-06-12T20:33:04-05:00
#
# HITL:
# 3ad37a3 2026-07-14T02:19:30-05:00
# --------------------------------------------------

AUTORESEARCH_START = datetime.fromisoformat(
    "2026-06-13T01:33:04+00:00"
)

HITL_START = datetime.fromisoformat(
    "2026-07-14T07:19:30+00:00"
)


def parse_dt(x):
    if not x:
        return None
    return datetime.fromisoformat(
        x.replace("Z", "+00:00")
    )


manifest = {
    r["name"]: r
    for r in json.load(open(MANIFEST))
}

rows = list(
    csv.DictReader(open(SIGNALS))
)


for r in rows:

    repo_name = r["repo_name"]
    meta = manifest[repo_name]

    created = parse_dt(
        meta.get("created_at")
    )

    r["repo_created_at"] = (
        meta.get("created_at") or ""
    )

    r["repo_pushed_at"] = (
        meta.get("pushed_at") or ""
    )

    # ==============================================
    # Determine historical capability era
    # ==============================================

    if created is None:

        era = "unknown"
        possible = (
            "standard|autoresearch|hitl"
        )

    elif created < AUTORESEARCH_START:

        era = "pre_autoresearch"
        possible = "standard"

    elif created < HITL_START:

        era = "autoresearch_available"
        possible = (
            "standard|autoresearch"
        )

    else:

        era = "hitl_available"
        possible = (
            "standard|autoresearch|hitl"
        )

    r["capability_era"] = era
    r["possible_modes_by_time"] = possible


    # ==============================================
    # Final classification
    #
    # Structural runtime evidence has precedence.
    # ==============================================

    structural_mode = r["mode"]

    if structural_mode == "hitl":

        r["final_mode"] = "hitl"
        r["final_confidence"] = "high"
        r["mode_source"] = (
            "runtime_hitl_artifact"
        )

    elif structural_mode == "autoresearch":

        r["final_mode"] = "autoresearch"
        r["final_confidence"] = "high"
        r["mode_source"] = (
            "runtime_autoresearch_artifact"
        )

    elif structural_mode == "standard":

        r["final_mode"] = "standard"
        r["final_confidence"] = (
            r["confidence"]
        )
        r["mode_source"] = (
            "runtime_standard_structure"
        )

    # ==============================================
    # Historical inference:
    #
    # If an executed trajectory predates the
    # existence of AutoResearch, Standard is the
    # only possible NeuriCo mode.
    # ==============================================

    elif (
        r["repo_status"] == "executed"
        and era == "pre_autoresearch"
    ):

        r["final_mode"] = "standard"
        r["final_confidence"] = "high"
        r["mode_source"] = (
            "historical_pre_autoresearch"
        )

    else:

        r["final_mode"] = "unknown"
        r["final_confidence"] = "low"
        r["mode_source"] = (
            "historical_constraint_only"
        )


# --------------------------------------------------
# Write
# --------------------------------------------------

fields = list(rows[0].keys())

with OUT.open("w", newline="") as f:

    writer = csv.DictWriter(
        f,
        fieldnames=fields
    )

    writer.writeheader()
    writer.writerows(rows)


# --------------------------------------------------
# Reporting
# --------------------------------------------------

print("\nFINAL MODE COUNTS")
print("-----------------")

for k, v in Counter(
    r["final_mode"]
    for r in rows
).most_common():

    print(f"{k:25s} {v:5d}")


print("\nCAPABILITY ERA")
print("-----------------")

for k, v in Counter(
    r["capability_era"]
    for r in rows
).most_common():

    print(f"{k:25s} {v:5d}")


print("\nMODE SOURCE")
print("-----------------")

for k, v in Counter(
    r["mode_source"]
    for r in rows
).most_common():

    print(f"{k:35s} {v:5d}")


# Executed but unresolved
unresolved = [
    r for r in rows
    if (
        r["repo_status"] == "executed"
        and r["final_mode"] == "unknown"
    )
]

print(
    "\nEXECUTED UNKNOWN:",
    len(unresolved)
)


# Split unresolved by era
print("\nEXECUTED UNKNOWN BY ERA")
print("-----------------------")

counts = Counter(
    r["capability_era"]
    for r in unresolved
)

for k, v in counts.most_common():
    print(f"{k:25s} {v:5d}")


# Examples
groups = defaultdict(list)

for r in unresolved:
    groups[
        r["capability_era"]
    ].append(r)

for era, group in groups.items():

    print(
        f"\n{era}: {len(group)}"
    )

    for r in group[:15]:

        print(
            " ",
            r["repo_created_at"],
            r["repo_name"],
            "=>",
            r["possible_modes_by_time"]
        )


print("\nWrote:", OUT)
