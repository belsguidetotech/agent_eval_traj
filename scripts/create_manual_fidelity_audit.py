from __future__ import annotations

import csv
import json
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path("data/cache/repo_metadata")
EVENTS = Path("data/processed/canonical_events_v1.jsonl")

OUT_DIR = Path("results/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = OUT_DIR / "manual_fidelity_sample.csv"
OUT_JSONL = OUT_DIR / "manual_fidelity_sample.jsonl"

SEED = 20260829

PROVIDERS = [
    "claude",
    "codex",
    "gemini",
]

# 30 events/provider.
#
# We intentionally oversample less-common event classes instead
# of drawing 90 events uniformly from the corpus.
QUOTAS = {
    "tool_call": 7,
    "tool_result": 7,
    "message": 6,
    "status": 4,
    "error": 3,
    "artifact_change": 1,
    "other": 2,
}

TARGET_PER_PROVIDER = 30

# Keep a reasonably large reservoir so rare strata can be sampled.
RESERVOIR_SIZE = 100


# ============================================================
# Sampling
# ============================================================

def reservoir_add(
    bucket,
    seen,
    item,
    rng,
):
    seen += 1

    if len(bucket) < RESERVOIR_SIZE:
        bucket.append(item)
    else:
        j = rng.randrange(seen)

        if j < RESERVOIR_SIZE:
            bucket[j] = item

    return seen


def sample_events():

    rng = random.Random(SEED)

    reservoirs = defaultdict(list)
    seen = defaultdict(int)

    total = 0
    provider_counts = Counter()
    event_type_counts = Counter()

    with EVENTS.open(
        encoding="utf-8"
    ) as f:

        for line in f:

            if not line.strip():
                continue

            event = json.loads(line)

            provider = str(
                event.get(
                    "provider",
                    ""
                )
            ).lower()

            if provider not in PROVIDERS:
                continue

            event_type = str(
                event.get(
                    "event_type",
                    "other",
                )
            )

            key = (
                provider,
                event_type,
            )

            seen[key] = reservoir_add(
                reservoirs[key],
                seen[key],
                event,
                rng,
            )

            total += 1
            provider_counts[provider] += 1
            event_type_counts[event_type] += 1


    selected = []


    for provider in PROVIDERS:

        provider_selected = []
        used_ids = set()

        # ----------------------------------------------------
        # Primary stratified quotas
        # ----------------------------------------------------

        for (
            event_type,
            quota,
        ) in QUOTAS.items():

            bucket = list(
                reservoirs.get(
                    (
                        provider,
                        event_type,
                    ),
                    [],
                )
            )

            rng.shuffle(bucket)

            take = min(
                quota,
                len(bucket),
            )

            for event in bucket[:take]:

                event_id = event[
                    "event_id"
                ]

                if event_id in used_ids:
                    continue

                provider_selected.append(
                    event
                )

                used_ids.add(
                    event_id
                )


        # ----------------------------------------------------
        # Fill shortages to exactly 30
        # ----------------------------------------------------

        if (
            len(provider_selected)
            < TARGET_PER_PROVIDER
        ):

            leftovers = []

            for (
                p,
                _
            ), bucket in reservoirs.items():

                if p != provider:
                    continue

                for event in bucket:

                    if (
                        event["event_id"]
                        not in used_ids
                    ):
                        leftovers.append(
                            event
                        )

            rng.shuffle(leftovers)

            needed = (
                TARGET_PER_PROVIDER
                - len(provider_selected)
            )

            for event in leftovers[:needed]:

                provider_selected.append(
                    event
                )

                used_ids.add(
                    event["event_id"]
                )


        if (
            len(provider_selected)
            != TARGET_PER_PROVIDER
        ):
            raise RuntimeError(
                f"Could not sample "
                f"{TARGET_PER_PROVIDER} "
                f"events for {provider}; "
                f"got "
                f"{len(provider_selected)}"
            )


        selected.extend(
            provider_selected
        )


    rng.shuffle(selected)

    print(
        "Canonical events scanned:",
        total,
    )

    print(
        "Provider counts:",
        dict(provider_counts),
    )

    print(
        "Event-type counts:",
        dict(event_type_counts),
    )

    return selected


# ============================================================
# Raw-record retrieval
# ============================================================

RAW_CACHE = {}


def git_show_records(
    repository_id: str,
    transcript_path: str,
):
    """
    Reproduce the extractor's raw-record indexing exactly:

    1. git show the committed transcript
    2. ignore blank lines
    3. ignore non-JSON lines
    4. append successfully parsed JSON values to records
    5. raw_record_index indexes this filtered list
    """

    key = (
        repository_id,
        transcript_path,
    )

    if key in RAW_CACHE:
        return RAW_CACHE[key]

    repo = (
        ROOT
        / repository_id
    )

    p = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "show",
            f"HEAD:{transcript_path}",
        ],
        capture_output=True,
        text=True,
    )

    if p.returncode != 0:

        result = {
            "records": None,
            "error": p.stderr.strip(),
            "non_json_count": 0,
        }

        RAW_CACHE[key] = result
        return result


    records = []
    non_json_count = 0

    for physical_line_no, line in enumerate(
        p.stdout.splitlines(),
        start=1,
    ):

        if not line.strip():
            continue

        try:
            obj = json.loads(line)

        except json.JSONDecodeError:
            non_json_count += 1
            continue

        records.append({
            "raw_json": obj,
            "raw_line": line,
            "physical_line_no":
                physical_line_no,
        })


    result = {
        "records": records,
        "error": None,
        "non_json_count": non_json_count,
    }

    RAW_CACHE[key] = result

    return result


def get_raw_record(
    event,
):

    repo = event[
        "repository_id"
    ]

    path = event[
        "transcript_path"
    ]

    raw_index = int(
        event[
            "raw_record_index"
        ]
    )

    result = git_show_records(
        repo,
        path,
    )

    records = result[
        "records"
    ]


    if records is None:

        return {
            "raw_lookup_status":
                "git_show_failed",

            "raw_lookup_error":
                result["error"],

            "raw_line":
                "",

            "raw_json":
                None,

            "raw_physical_line_no":
                None,

            "transcript_non_json_lines":
                result[
                    "non_json_count"
                ],
        }


    if (
        raw_index < 0
        or raw_index >= len(records)
    ):

        return {
            "raw_lookup_status":
                "index_out_of_range",

            "raw_lookup_error":
                (
                    f"raw_index={raw_index}; "
                    f"json_records={len(records)}"
                ),

            "raw_line":
                "",

            "raw_json":
                None,

            "raw_physical_line_no":
                None,

            "transcript_non_json_lines":
                result[
                    "non_json_count"
                ],
        }


    record = records[
        raw_index
    ]

    return {
        "raw_lookup_status":
            "ok",

        "raw_lookup_error":
            "",

        "raw_line":
            record[
                "raw_line"
            ],

        "raw_json":
            record[
                "raw_json"
            ],

        "raw_physical_line_no":
            record[
                "physical_line_no"
            ],

        "transcript_non_json_lines":
            result[
                "non_json_count"
            ],
    }

# ============================================================
# Compact display helpers
# ============================================================

def compact_json(
    value,
    limit=1800,
):

    if value is None:
        return ""

    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )

    text = text.replace(
        "\n",
        "\\n",
    )

    return text[:limit]


def canonical_summary(
    event,
):

    fields = {
        "actor":
            event.get("actor"),

        "event_type":
            event.get("event_type"),

        "action_type":
            event.get("action_type"),

        "tool_name":
            event.get("tool_name"),

        "action":
            event.get("action"),

        "observation":
            event.get("observation"),

        "artifact":
            event.get("artifact"),

        "status":
            event.get("status"),

        "error_type":
            event.get("error_type"),

        "tool_call_id":
            event.get("tool_call_id"),

        "parent_event_id":
            event.get(
                "parent_event_id"
            ),
    }

    return compact_json(
        fields,
        limit=1800,
    )


# ============================================================
# Main
# ============================================================

def main():

    selected = sample_events()

    rows = []
    json_rows = []

    lookup_counts = Counter()


    for i, event in enumerate(
        selected,
        start=1,
    ):

        raw = get_raw_record(
            event
        )

        lookup_counts[
            raw[
                "raw_lookup_status"
            ]
        ] += 1


        row = {
            "audit_id":
                f"A{i:03d}",

            # -----------------------------------------------
            # Identity
            # -----------------------------------------------

            "repository_id":
                event.get(
                    "repository_id",
                    "",
                ),

            "provider":
                event.get(
                    "provider",
                    "",
                ),

            "stage":
                event.get(
                    "stage",
                    "",
                ),

            "trajectory_id":
                event.get(
                    "trajectory_id",
                    "",
                ),

            "transcript_path":
                event.get(
                    "transcript_path",
                    "",
                ),

            "raw_record_index":
                event.get(
                    "raw_record_index",
                    "",
                ),

            "raw_physical_line_no":
                raw.get(
                    "raw_physical_line_no",
                    "",
                ),

            "transcript_non_json_lines":
                raw.get(
                    "transcript_non_json_lines",
                    0,
                ),

            "raw_sub_event_index":
                event.get(
                    "raw_sub_event_index",
                    "",
                ),

            "canonical_event_index":
                event.get(
                    "canonical_event_index",
                    "",
                ),

            "event_id":
                event.get(
                    "event_id",
                    "",
                ),

            # -----------------------------------------------
            # Canonical labels
            # -----------------------------------------------

            "event_type":
                event.get(
                    "event_type",
                    "",
                ),

            "action_type":
                event.get(
                    "action_type",
                    "",
                ),

            "tool_name":
                event.get(
                    "tool_name",
                    "",
                ),

            "tool_call_id":
                event.get(
                    "tool_call_id",
                    "",
                ),

            "parent_event_id":
                event.get(
                    "parent_event_id",
                    "",
                ),

            "raw_type":
                event.get(
                    "raw_type",
                    "",
                ),

            "raw_role":
                event.get(
                    "raw_role",
                    "",
                ),

            # -----------------------------------------------
            # Side-by-side evidence
            # -----------------------------------------------

            "raw_lookup_status":
                raw[
                    "raw_lookup_status"
                ],

            "raw_lookup_error":
                raw[
                    "raw_lookup_error"
                ],

            "raw_excerpt":
                compact_json(
                    raw[
                        "raw_json"
                    ]
                    if raw[
                        "raw_json"
                    ]
                    is not None
                    else raw[
                        "raw_line"
                    ],
                    1800,
                ),

            "canonical_excerpt":
                canonical_summary(
                    event
                ),

            # -----------------------------------------------
            # Manual review
            #
            # Fill with:
            # Y / N / NA
            # -----------------------------------------------

            "event_type_correct":
                "",

            "action_type_correct":
                "",

            "content_preserved":
                "",

            "linkage_correct":
                "",

            "notes":
                "",
        }

        rows.append(row)


        json_rows.append({
            "audit_id":
                row[
                    "audit_id"
                ],

            "raw":
                raw[
                    "raw_json"
                ],

            "canonical":
                event,

            "review": {
                "event_type_correct":
                    None,

                "action_type_correct":
                    None,

                "content_preserved":
                    None,

                "linkage_correct":
                    None,

                "notes":
                    None,
            },
        })


    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    with OUT_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(
                rows[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


    # --------------------------------------------------------
    # JSONL
    # --------------------------------------------------------

    with OUT_JSONL.open(
        "w",
        encoding="utf-8",
    ) as f:

        for row in json_rows:

            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


    print(
        "\nAudit sample:"
    )

    print(
        "N =",
        len(rows),
    )

    print(
        "Raw lookup:",
        dict(lookup_counts),
    )


    print(
        "\nBy provider:"
    )

    for provider in PROVIDERS:

        sub = [
            x
            for x in rows
            if x["provider"]
            == provider
        ]

        counts = Counter(
            x["event_type"]
            for x in sub
        )

        print(
            provider,
            len(sub),
            dict(
                sorted(
                    counts.items()
                )
            ),
        )


    print(
        "\nWrote:"
    )

    print(
        OUT_CSV
    )

    print(
        OUT_JSONL
    )


if __name__ == "__main__":
    main()