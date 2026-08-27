from pathlib import Path
import subprocess
import csv
from datetime import datetime, timezone
from collections import Counter

ROOT = Path("data/cache/repo_metadata")
CATALOG = Path("results/statistics/trajectory_catalog.csv")
OUT = Path("results/reconnaissance/standard_only_verification.csv")

AR_START = datetime.fromisoformat(
    "2026-06-13T01:33:04+00:00"
)

HITL_START = datetime.fromisoformat(
    "2026-07-14T07:19:30+00:00"
)


def dt(x):
    if not x:
        return None

    d = datetime.fromisoformat(
        x.replace("Z", "+00:00")
    )

    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)

    return d


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
        return ""

    return p.stdout


rows = list(csv.DictReader(CATALOG.open()))

included = [
    r for r in rows
    if r["include_in_analysis"] == "True"
]

audit = []

for r in included:

    name = r["repo_name"]
    repo = ROOT / name
    paths = git_tree(repo)

    low = [p.lower() for p in paths]

    run_time = dt(r["run_created_at"])

    # ------------------------------------------
    # STRICT runtime-path evidence only
    # ------------------------------------------

    hitl_paths = [
        p for p in low
        if (
            p.startswith(".neurico/hitl/")
            or p.startswith("logs/hitl/")
            or "hitl-launch" in p
            or "hitl-launch-requests" in p
        )
    ]

    autoresearch_paths = [
        p for p in low
        if (
            p.startswith("logs/experiment-autoresearch/")
            or "/experiment-autoresearch/" in p
        )
    ]

    # ------------------------------------------
    # Inspect NeuriCo runtime metadata contents.
    # Do NOT grep research papers/code.
    # ------------------------------------------

    runtime_text = []

    for p in paths:
        lp = p.lower()

        if (
            lp.startswith(".neurico/")
            and (
                lp.endswith(".json")
                or lp.endswith(".yaml")
                or lp.endswith(".yml")
            )
        ):
            runtime_text.append(
                git_show(repo, p).lower()
            )

    runtime_text = "\n".join(runtime_text)

    content_auto = any(
        marker in runtime_text
        for marker in [
            '"autoresearch"',
            "'autoresearch'",
            "experiment-autoresearch",
            "autoresearch_iterations",
            "autoresearch-iterations",
        ]
    )

    content_hitl = any(
        marker in runtime_text
        for marker in [
            '"hitl"',
            "'hitl'",
            "hitl_mode",
            "ask_human",
            "hitl-launch",
        ]
    )

    has_auto = (
        bool(autoresearch_paths)
        or content_auto
    )

    has_hitl = (
        bool(hitl_paths)
        or content_hitl
    )

    # ------------------------------------------
    # Temporal category
    # ------------------------------------------

    if run_time is None:
        era = "legacy_no_exact_run_time"

    elif run_time < AR_START:
        era = "pre_autoresearch"

    elif run_time < HITL_START:
        era = "autoresearch_available"

    else:
        era = "hitl_available"

    suspicious = has_auto or has_hitl

    audit.append({
        "repo_name": name,
        "run_created_at": r["run_created_at"],
        "era": era,

        "has_autoresearch_runtime_path": bool(
            autoresearch_paths
        ),

        "has_hitl_runtime_path": bool(
            hitl_paths
        ),

        "has_autoresearch_runtime_content":
            content_auto,

        "has_hitl_runtime_content":
            content_hitl,

        "suspicious_nonstandard": suspicious,

        "autoresearch_examples":
            "|".join(autoresearch_paths[:5]),

        "hitl_examples":
            "|".join(hitl_paths[:5]),
    })


with OUT.open("w", newline="") as f:
    w = csv.DictWriter(
        f,
        fieldnames=audit[0].keys()
    )
    w.writeheader()
    w.writerows(audit)


print("TOTAL ANALYZED:", len(audit))

print("\nERA")
print("---")
for k, v in Counter(
    r["era"] for r in audit
).most_common():
    print(f"{k:30s} {v:5d}")


suspicious = [
    r for r in audit
    if r["suspicious_nonstandard"]
]

print("\nSUSPICIOUS NON-STANDARD:", len(suspicious))

for r in suspicious:
    print(
        r["repo_name"],
        r["era"],
        "AR_path=", r["has_autoresearch_runtime_path"],
        "AR_content=", r["has_autoresearch_runtime_content"],
        "HITL_path=", r["has_hitl_runtime_path"],
        "HITL_content=", r["has_hitl_runtime_content"],
    )


post_ar = [
    r for r in audit
    if r["era"] in {
        "autoresearch_available",
        "hitl_available"
    }
]

print("\nPOST-AUTORESEARCH RUNS:", len(post_ar))

clean_post_ar = [
    r for r in post_ar
    if not r["suspicious_nonstandard"]
]

print(
    "POST-AUTORESEARCH WITH NO ALT-MODE EVIDENCE:",
    len(clean_post_ar)
)

print("\nWrote:", OUT)
