from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


# ============================================================
# Paths
# ============================================================

EVENTS = Path(
    "data/processed/canonical_events_v1.jsonl"
)

FIDELITY = Path(
    "results/validation/"
    "manual_fidelity_summary.csv"
)

OUT = Path(
    "results/paper"
)

OUT.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# Frozen corpus-level inventory
#
# These values come from the completed corpus reconnaissance /
# extraction QC, rather than from canonical_events_v1.jsonl
# alone.
#
# Important:
# canonical_events_v1.jsonl cannot recover repositories /
# trajectories that produced zero canonical events.
# ============================================================

CORPUS = {
    "analysis_repositories": 467,
    "repositories_with_runtime_transcripts": 462,
    "provider_trajectories_with_transcripts": 469,
    "transcript_files": 923,
    "raw_json_records": 229365,
    "non_json_lines": 21773,
}


# ============================================================
# Expected canonical extraction results
#
# Assertions prevent paper numbers from silently drifting.
# ============================================================

EXPECTED = {
    "canonical_events": 223658,
    "event_bearing_trajectories": 455,
    "repositories_with_canonical_events": 448,

    "claude_events": 163320,
    "codex_events": 32850,
    "gemini_events": 27488,

    "tool_call": 67488,
    "tool_result": 63145,
    "status": 46054,
    "message": 39582,
    "error": 4387,
    "other": 1959,
    "artifact_change": 1043,
}


PROVIDERS = [
    "claude",
    "codex",
    "gemini",
]

EVENT_TYPES = [
    "message",
    "tool_call",
    "tool_result",
    "artifact_change",
    "error",
    "status",
    "other",
]


# ============================================================
# Helpers
# ============================================================

def pct(
    numerator,
    denominator,
):
    if not denominator:
        return 0.0

    return (
        100.0
        * numerator
        / denominator
    )


def write_csv(
    path,
    rows,
    fieldnames,
):
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


def latex_escape(value):
    text = str(value)

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    return text


def write_simple_latex_table(
    path,
    headers,
    rows,
    align,
    caption,
    label,
):
    lines = []

    lines.append(
        r"\begin{table}[t]"
    )
    lines.append(
        r"\centering"
    )
    lines.append(
        r"\small"
    )

    lines.append(
        rf"\begin{{tabular}}{{{align}}}"
    )

    lines.append(
        r"\toprule"
    )

    lines.append(
        " & ".join(
            latex_escape(x)
            for x in headers
        )
        + r" \\"
    )

    lines.append(
        r"\midrule"
    )

    for row in rows:

        lines.append(
            " & ".join(
                str(x)
                for x in row
            )
            + r" \\"
        )

    lines.append(
        r"\bottomrule"
    )

    lines.append(
        r"\end{tabular}"
    )

    lines.append(
        rf"\caption{{{caption}}}"
    )

    lines.append(
        rf"\label{{{label}}}"
    )

    lines.append(
        r"\end{table}"
    )

    path.write_text(
        "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )


# ============================================================
# Stream canonical events once
# ============================================================

total_events = 0

provider_counts = Counter()
event_type_counts = Counter()

provider_event_counts = defaultdict(
    Counter
)

repositories = set()
trajectories = set()

transitions = Counter()

previous_by_trajectory = {}

tool_calls = 0
tool_results = 0

tool_calls_with_action_type = 0
tool_calls_with_tool_name = 0
tool_calls_with_call_id = 0

tool_results_with_parent = 0


with EVENTS.open(
    encoding="utf-8"
) as f:

    for line in f:

        if not line.strip():
            continue

        event = json.loads(line)

        total_events += 1

        provider = str(
            event.get(
                "provider",
                "unknown",
            )
        )

        event_type = str(
            event.get(
                "event_type",
                "other",
            )
        )

        repository_id = str(
            event.get(
                "repository_id",
                "",
            )
        )

        trajectory_id = str(
            event.get(
                "trajectory_id",
                "",
            )
        )

        provider_counts[
            provider
        ] += 1

        event_type_counts[
            event_type
        ] += 1

        provider_event_counts[
            provider
        ][
            event_type
        ] += 1


        if repository_id:
            repositories.add(
                repository_id
            )

        if trajectory_id:
            trajectories.add(
                trajectory_id
            )


        # ----------------------------------------------------
        # Downstream structural coverage
        # ----------------------------------------------------

        if event_type == "tool_call":

            tool_calls += 1

            if event.get(
                "action_type"
            ):
                tool_calls_with_action_type += 1

            if event.get(
                "tool_name"
            ):
                tool_calls_with_tool_name += 1

            if event.get(
                "tool_call_id"
            ):
                tool_calls_with_call_id += 1


        elif event_type == "tool_result":

            tool_results += 1

            if event.get(
                "parent_event_id"
            ):
                tool_results_with_parent += 1


        # ----------------------------------------------------
        # Trajectory transition
        #
        # We use trajectory_id so transitions never cross
        # provider trajectories.
        # ----------------------------------------------------

        if trajectory_id:

            previous = (
                previous_by_trajectory.get(
                    trajectory_id
                )
            )

            if previous is not None:

                transitions[
                    (
                        previous,
                        event_type,
                    )
                ] += 1

            previous_by_trajectory[
                trajectory_id
            ] = event_type


# ============================================================
# Assertions
# ============================================================

assert (
    total_events
    == EXPECTED[
        "canonical_events"
    ]
), (
    total_events,
    EXPECTED["canonical_events"],
)

assert (
    len(trajectories)
    == EXPECTED[
        "event_bearing_trajectories"
    ]
), len(trajectories)

assert (
    len(repositories)
    == EXPECTED[
        "repositories_with_canonical_events"
    ]
), len(repositories)


for provider in PROVIDERS:

    expected = EXPECTED[
        f"{provider}_events"
    ]

    actual = provider_counts[
        provider
    ]

    assert (
        actual == expected
    ), (
        provider,
        actual,
        expected,
    )


for event_type in EVENT_TYPES:

    actual = event_type_counts[
        event_type
    ]

    expected = EXPECTED[
        event_type
    ]

    assert (
        actual == expected
    ), (
        event_type,
        actual,
        expected,
    )


# ============================================================
# TABLE 1
# Corpus + canonicalization coverage
# ============================================================

unknown_fraction = pct(
    event_type_counts[
        "other"
    ],
    total_events,
)


table1_rows = [
    {
        "statistic":
            "Analysis repositories",
        "value":
            CORPUS[
                "analysis_repositories"
            ],
    },

    {
        "statistic":
            "Repositories with runtime transcripts",
        "value":
            CORPUS[
                "repositories_with_runtime_transcripts"
            ],
    },

    {
        "statistic":
            "Provider trajectories with transcripts",
        "value":
            CORPUS[
                "provider_trajectories_with_transcripts"
            ],
    },

    {
        "statistic":
            "Event-bearing provider trajectories",
        "value":
            len(trajectories),
    },

    {
        "statistic":
            "Repositories with canonical events",
        "value":
            len(repositories),
    },

    {
        "statistic":
            "Transcript files",
        "value":
            CORPUS[
                "transcript_files"
            ],
    },

    {
        "statistic":
            "Raw JSON records",
        "value":
            CORPUS[
                "raw_json_records"
            ],
    },

    {
        "statistic":
            "Non-JSON transcript lines",
        "value":
            CORPUS[
                "non_json_lines"
            ],
    },

    {
        "statistic":
            "Canonical events",
        "value":
            total_events,
    },

    {
        "statistic":
            "Claude events",
        "value":
            provider_counts[
                "claude"
            ],
    },

    {
        "statistic":
            "Codex events",
        "value":
            provider_counts[
                "codex"
            ],
    },

    {
        "statistic":
            "Gemini events",
        "value":
            provider_counts[
                "gemini"
            ],
    },

    {
        "statistic":
            "Residual other events",
        "value":
            (
                f"{event_type_counts['other']:,} "
                f"({unknown_fraction:.3f}%)"
            ),
    },

    {
        "statistic":
            "Parse exceptions",
        "value":
            0,
    },

    {
        "statistic":
            "Duplicate event IDs",
        "value":
            0,
    },
]


write_csv(
    OUT
    / "table1_corpus_summary.csv",

    table1_rows,

    [
        "statistic",
        "value",
    ],
)


latex_table1 = []

for row in table1_rows:

    value = row[
        "value"
    ]

    if isinstance(
        value,
        int,
    ):
        value = f"{value:,}"

    else:
        value = latex_escape(
            value
        )

    latex_table1.append([
        latex_escape(
            row[
                "statistic"
            ]
        ),
        value,
    ])


write_simple_latex_table(
    OUT
    / "table1_corpus_summary.tex",

    [
        "Statistic",
        "Value",
    ],

    latex_table1,

    "lr",

    (
        "Corpus and canonicalization coverage. "
        "Repositories and trajectories with zero "
        "canonical events are retained in the "
        "corpus-level denominators."
    ),

    "tab:corpus",
)


# ============================================================
# TABLE 1B / appendix:
# Event-type distribution
# ============================================================

table_event_rows = []

for event_type in EVENT_TYPES:

    count = event_type_counts[
        event_type
    ]

    table_event_rows.append({
        "event_type":
            event_type,

        "count":
            count,

        "share_pct":
            round(
                pct(
                    count,
                    total_events,
                ),
                3,
            ),
    })


write_csv(
    OUT
    / "table_event_distribution.csv",

    table_event_rows,

    [
        "event_type",
        "count",
        "share_pct",
    ],
)


latex_event_rows = []

for row in table_event_rows:

    latex_event_rows.append([
        latex_escape(
            row[
                "event_type"
            ]
        ),

        f"{row['count']:,}",

        f"{row['share_pct']:.2f}\\%",
    ])


write_simple_latex_table(
    OUT
    / "table_event_distribution.tex",

    [
        "Event type",
        "Count",
        "Share",
    ],

    latex_event_rows,

    "lrr",

    (
        "Distribution of canonical event types "
        "across the full event-bearing corpus."
    ),

    "tab:event_distribution",
)


# ============================================================
# TABLE 2
# Fidelity audit
# ============================================================

raw_fidelity_rows = list(
    csv.DictReader(
        FIDELITY.open(
            encoding="utf-8"
        )
    )
)


metric_names = {
    "event_type_fidelity":
        "Event-type fidelity",

    "action_type_fidelity":
        "Action-type fidelity",

    "content_preservation":
        "Content preservation",

    "linkage_fidelity":
        "Linkage fidelity",
}


fidelity_lookup = {}

for row in raw_fidelity_rows:

    provider = row[
        "provider"
    ]

    metric = row[
        "metric"
    ]

    accuracy = row[
        "accuracy"
    ]

    if accuracy == "":
        continue

    fidelity_lookup[
        (
            metric,
            provider,
        )
    ] = {
        "correct":
            int(
                row[
                    "correct"
                ]
            ),

        "applicable":
            int(
                row[
                    "applicable"
                ]
            ),

        "accuracy":
            float(
                accuracy
            ),
    }


table2_rows = []

for metric in [
    "event_type_fidelity",
    "action_type_fidelity",
    "content_preservation",
    "linkage_fidelity",
]:

    row = {
        "metric":
            metric_names[
                metric
            ]
    }

    for provider in [
        "overall",
        "claude",
        "codex",
        "gemini",
    ]:

        result = fidelity_lookup[
            (
                metric,
                provider,
            )
        ]

        row[
            provider
        ] = (
            100.0
            * result[
                "accuracy"
            ]
        )

        row[
            f"{provider}_n"
        ] = (
            f"{result['correct']}/"
            f"{result['applicable']}"
        )

    table2_rows.append(
        row
    )


write_csv(
    OUT
    / "table2_fidelity.csv",

    table2_rows,

    [
        "metric",

        "overall",
        "overall_n",

        "claude",
        "claude_n",

        "codex",
        "codex_n",

        "gemini",
        "gemini_n",
    ],
)


latex_table2 = []

for row in table2_rows:

    latex_table2.append([
        latex_escape(
            row["metric"]
        ),

        (
            f"{row['overall']:.1f}\\% "
            f"({row['overall_n']})"
        ),

        (
            f"{row['claude']:.1f}\\% "
            f"({row['claude_n']})"
        ),

        (
            f"{row['codex']:.1f}\\% "
            f"({row['codex_n']})"
        ),

        (
            f"{row['gemini']:.1f}\\% "
            f"({row['gemini_n']})"
        ),
    ])


write_simple_latex_table(
    OUT
    / "table2_fidelity.tex",

    [
        "Metric",
        "Overall",
        "Claude",
        "Codex",
        "Gemini",
    ],

    latex_table2,

    "lrrrr",

    (
        "Stratified fidelity audit of 90 canonical "
        "events (30 per provider, spanning 74 "
        "repositories). Parentheses report "
        "correct/applicable judgments. "
        "Action-type and linkage metrics are "
        "evaluated only when applicable."
    ),

    "tab:fidelity",
)


# ============================================================
# TABLE 3
# Structural coverage / downstream readiness
# ============================================================

table3_rows = [
    {
        "property":
            "Tool calls with semantic action type",

        "numerator":
            tool_calls_with_action_type,

        "denominator":
            tool_calls,
    },

    {
        "property":
            "Tool calls with tool identity",

        "numerator":
            tool_calls_with_tool_name,

        "denominator":
            tool_calls,
    },

    {
        "property":
            "Tool calls with call identifier",

        "numerator":
            tool_calls_with_call_id,

        "denominator":
            tool_calls,
    },

    {
        "property":
            "Tool results with parent-event linkage",

        "numerator":
            tool_results_with_parent,

        "denominator":
            tool_results,
    },
]


for row in table3_rows:

    row[
        "coverage_pct"
    ] = round(
        pct(
            row[
                "numerator"
            ],
            row[
                "denominator"
            ],
        ),
        3,
    )


write_csv(
    OUT
    / "table3_structural_coverage.csv",

    table3_rows,

    [
        "property",
        "numerator",
        "denominator",
        "coverage_pct",
    ],
)


latex_table3 = []

for row in table3_rows:

    latex_table3.append([
        latex_escape(
            row[
                "property"
            ]
        ),

        (
            f"{row['numerator']:,}/"
            f"{row['denominator']:,}"
        ),

        (
            f"{row['coverage_pct']:.3f}\\%"
        ),
    ])


write_simple_latex_table(
    OUT
    / "table3_structural_coverage.tex",

    [
        "Canonical property",
        "Coverage",
        "Rate",
    ],

    latex_table3,

    "lrr",

    (
        "Structural coverage of canonical tool "
        "events for downstream trajectory analysis."
    ),

    "tab:structural_coverage",
)


# ============================================================
# FIGURE 2
# Provider-normalized event composition
#
# Use percentage points rather than unit fractions.
# No internal plot title: LaTeX caption will carry it.
# ============================================================

fig, ax = plt.subplots(
    figsize=(
        7.6,
        4.4,
    )
)


x = list(
    range(
        len(
            PROVIDERS
        )
    )
)


bottom = [
    0.0
    for _ in PROVIDERS
]


for event_type in EVENT_TYPES:

    values = []

    for provider in PROVIDERS:

        provider_total = (
            provider_counts[
                provider
            ]
        )

        share = pct(
            provider_event_counts[
                provider
            ][
                event_type
            ],
            provider_total,
        )

        values.append(
            share
        )


    ax.bar(
        x,
        values,
        bottom=bottom,
        label=event_type,
        width=0.72,
    )


    bottom = [
        a + b
        for a, b
        in zip(
            bottom,
            values,
        )
    ]


ax.set_xticks(
    x
)

ax.set_xticklabels(
    [
        "Claude",
        "Codex",
        "Gemini",
    ]
)

ax.set_xlabel(
    "Provider"
)

ax.set_ylabel(
    "Within-provider share of events (%)"
)

ax.set_ylim(
    0,
    100,
)

ax.legend(
    bbox_to_anchor=(
        1.02,
        1.0,
    ),
    loc="upper left",
    frameon=False,
)

fig.tight_layout()


fig.savefig(
    OUT
    / "fig2_event_composition_by_provider.pdf",

    bbox_inches="tight",
)

fig.savefig(
    OUT
    / "fig2_event_composition_by_provider.png",

    dpi=300,
    bbox_inches="tight",
)

plt.close(
    fig
)


# ============================================================
# FIGURE 3
# Row-normalized transition probability heatmap
#
# P(next event | current event)
#
# This avoids conflating transition structure with the
# marginal frequency of each source event.
# ============================================================

count_matrix = []

for source in EVENT_TYPES:

    row = []

    for target in EVENT_TYPES:

        row.append(
            transitions[
                (
                    source,
                    target,
                )
            ]
        )

    count_matrix.append(
        row
    )


prob_matrix = []

for row in count_matrix:

    row_total = sum(
        row
    )

    if row_total:

        prob_matrix.append([
            value / row_total
            for value in row
        ])

    else:

        prob_matrix.append([
            0.0
            for _ in row
        ])


fig, ax = plt.subplots(
    figsize=(
        7.0,
        5.8,
    )
)


im = ax.imshow(
    prob_matrix,
    aspect="auto",
    vmin=0,
    vmax=1,
)


ax.set_xticks(
    range(
        len(
            EVENT_TYPES
        )
    )
)

ax.set_yticks(
    range(
        len(
            EVENT_TYPES
        )
    )
)


ax.set_xticklabels(
    EVENT_TYPES,
    rotation=45,
    ha="right",
)

ax.set_yticklabels(
    EVENT_TYPES
)


ax.set_xlabel(
    "Next event"
)

ax.set_ylabel(
    "Current event"
)


# Annotate only meaningful cells.
#
# Keeping tiny probabilities unlabeled reduces clutter.
for i in range(
    len(
        EVENT_TYPES
    )
):

    for j in range(
        len(
            EVENT_TYPES
        )
    ):

        probability = (
            prob_matrix[
                i
            ][
                j
            ]
        )

        if probability >= 0.01:

            ax.text(
                j,
                i,
                f"{100 * probability:.1f}%",
                ha="center",
                va="center",
                fontsize=7,
            )


cbar = fig.colorbar(
    im,
    ax=ax,
)

cbar.set_label(
    "Conditional transition probability"
)


fig.tight_layout()


fig.savefig(
    OUT
    / "fig3_transition_probability_heatmap.pdf",

    bbox_inches="tight",
)

fig.savefig(
    OUT
    / "fig3_transition_probability_heatmap.png",

    dpi=300,
    bbox_inches="tight",
)

plt.close(
    fig
)


# ============================================================
# Top transition counts
#
# Retain raw counts separately for textual reporting.
# ============================================================

top_transition_rows = []

for (
    source,
    target,
), count in transitions.most_common(
    25
):

    source_total = sum(
        transitions[
            (
                source,
                t,
            )
        ]
        for t in EVENT_TYPES
    )

    probability = (
        count
        / source_total
        if source_total
        else 0.0
    )

    top_transition_rows.append({
        "source_event":
            source,

        "target_event":
            target,

        "count":
            count,

        "conditional_probability":
            probability,

        "conditional_probability_pct":
            round(
                100.0
                * probability,
                2,
            ),
    })


write_csv(
    OUT
    / "top_transitions.csv",

    top_transition_rows,

    [
        "source_event",
        "target_event",
        "count",
        "conditional_probability",
        "conditional_probability_pct",
    ],
)


# ============================================================
# Provider composition table
#
# Useful for Results text and appendix.
# ============================================================

provider_composition_rows = []

for provider in PROVIDERS:

    total = provider_counts[
        provider
    ]

    for event_type in EVENT_TYPES:

        count = (
            provider_event_counts[
                provider
            ][
                event_type
            ]
        )

        provider_composition_rows.append({
            "provider":
                provider,

            "event_type":
                event_type,

            "count":
                count,

            "provider_total":
                total,

            "share_pct":
                round(
                    pct(
                        count,
                        total,
                    ),
                    3,
                ),
        })


write_csv(
    OUT
    / "provider_event_composition.csv",

    provider_composition_rows,

    [
        "provider",
        "event_type",
        "count",
        "provider_total",
        "share_pct",
    ],
)


# ============================================================
# Paper-number report
# ============================================================

print()
print(
    "=" * 72
)

print(
    "PAPER ARTIFACT SUMMARY"
)

print(
    "=" * 72
)


print()
print(
    "Corpus"
)

print(
    "-" * 72
)

print(
    "Analysis repositories:",
    CORPUS[
        "analysis_repositories"
    ],
)

print(
    "Repositories with transcripts:",
    CORPUS[
        "repositories_with_runtime_transcripts"
    ],
)

print(
    "Provider trajectories with transcripts:",
    CORPUS[
        "provider_trajectories_with_transcripts"
    ],
)

print(
    "Event-bearing trajectories:",
    len(
        trajectories
    ),
)

print(
    "Repositories with canonical events:",
    len(
        repositories
    ),
)

print(
    "Canonical events:",
    f"{total_events:,}",
)


print()
print(
    "Event distribution"
)

print(
    "-" * 72
)

for row in table_event_rows:

    print(
        f"{row['event_type']:18s}"
        f"{row['count']:10,d}"
        f"{row['share_pct']:9.2f}%"
    )


print()
print(
    "Structural coverage"
)

print(
    "-" * 72
)

for row in table3_rows:

    print(
        f"{row['property']}: "
        f"{row['numerator']:,}/"
        f"{row['denominator']:,} "
        f"({row['coverage_pct']:.3f}%)"
    )


print()
print(
    "Top transitions"
)

print(
    "-" * 72
)

for row in top_transition_rows[:15]:

    print(
        f"{row['source_event']:18s}"
        f" -> "
        f"{row['target_event']:18s}"
        f" {row['count']:8,d}"
        f"  "
        f"P={row['conditional_probability_pct']:6.2f}%"
    )


print()
print(
    "Generated files"
)

print(
    "-" * 72
)

for path in sorted(
    OUT.iterdir()
):

    if path.is_file():
        print(
            path.name
        )
