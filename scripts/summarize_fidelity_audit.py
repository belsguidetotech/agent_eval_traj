import csv
from collections import defaultdict
from pathlib import Path

INPUT = Path(
    "results/validation/"
    "manual_fidelity_sample_reviewed.csv"
)

OUTPUT = Path(
    "results/validation/"
    "manual_fidelity_summary.csv"
)

rows = list(
    csv.DictReader(
        INPUT.open(encoding="utf-8")
    )
)

METRICS = [
    (
        "event_type_correct",
        "event_type_fidelity",
    ),
    (
        "action_type_correct",
        "action_type_fidelity",
    ),
    (
        "content_preserved",
        "content_preservation",
    ),
    (
        "linkage_correct",
        "linkage_fidelity",
    ),
]

providers = [
    "overall",
    "claude",
    "codex",
    "gemini",
]

out = []

for provider in providers:

    subset = (
        rows
        if provider == "overall"
        else [
            r
            for r in rows
            if r["provider"] == provider
        ]
    )

    for column, metric in METRICS:

        applicable = [
            r
            for r in subset
            if r[column] in {"Y", "N"}
        ]

        correct = sum(
            r[column] == "Y"
            for r in applicable
        )

        n = len(applicable)

        out.append({
            "provider": provider,
            "metric": metric,
            "correct": correct,
            "applicable": n,
            "accuracy": (
                correct / n
                if n
                else ""
            ),
        })

with OUTPUT.open(
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "provider",
            "metric",
            "correct",
            "applicable",
            "accuracy",
        ],
    )

    writer.writeheader()
    writer.writerows(out)

print(
    f"Audit rows: {len(rows)}"
)

print(
    "Repositories:",
    len({
        r["repository_id"]
        for r in rows
    }),
)

print()

for row in out:

    if row["provider"] != "overall":
        continue

    print(
        f"{row['metric']:25s} "
        f"{row['correct']:2d}/"
        f"{row['applicable']:2d} "
        f"= "
        f"{100 * row['accuracy']:.1f}%"
    )

print(
    "\nWrote:",
    OUTPUT,
)
