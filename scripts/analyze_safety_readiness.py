import json
from collections import Counter
from pathlib import Path

INPUT = Path(
    "data/processed/canonical_events_v1.jsonl"
)

OUT = Path(
    "results/validation/"
    "safety_readiness_summary.json"
)


def text(e):
    return " ".join(
        str(e.get(k) or "")
        for k in [
            "tool_name",
            "action",
            "observation",
            "artifact",
        ]
    ).lower()


def is_external_source(e):
    """
    Coarse downstream enrichment.

    Not part of canonical extraction itself.
    """
    s = text(e)

    return any(
        x in s
        for x in [
            "http://",
            "https://",
            "web",
            "browser",
            "search",
            "email",
        ]
    )


def is_sensitive_sink(e):
    """
    Coarse safety-oriented enrichment.

    We only test whether the canonical event
    contains enough semantics to identify
    candidate sensitive operations.
    """
    action_type = str(
        e.get("action_type") or ""
    ).lower()

    s = text(e)

    sensitive_terms = [
        "secret",
        "credential",
        "token",
        "password",
        ".env",
        "api_key",
        "private",
    ]

    dangerous_actions = {
        "read",
        "write",
        "edit",
        "execute",
    }

    return (
        action_type in dangerous_actions
        and any(
            term in s
            for term in sensitive_terms
        )
    )


counts = Counter()

providers = Counter()

examples_source = []
examples_sink = []

with INPUT.open(
    encoding="utf-8"
) as f:

    for line in f:

        if not line.strip():
            continue

        e = json.loads(line)

        counts["events"] += 1

        provider = str(
            e.get("provider")
        )

        providers[provider] += 1


        if e.get("event_type") == "tool_call":

            counts["tool_calls"] += 1

            if e.get("action_type"):
                counts[
                    "tool_calls_with_action_type"
                ] += 1

            if e.get("tool_name"):
                counts[
                    "tool_calls_with_tool_name"
                ] += 1

            if e.get("tool_call_id"):
                counts[
                    "tool_calls_with_call_id"
                ] += 1


        if e.get("event_type") == "tool_result":

            counts["tool_results"] += 1

            if e.get("parent_event_id"):
                counts[
                    "tool_results_with_parent"
                ] += 1


        if is_external_source(e):

            counts[
                "heuristic_source_keyword_matches"
            ] += 1

            if len(examples_source) < 5:
                examples_source.append({
                    "event_id":
                        e.get("event_id"),

                    "provider":
                        e.get("provider"),

                    "event_type":
                        e.get("event_type"),

                    "tool_name":
                        e.get("tool_name"),

                    "action_type":
                        e.get("action_type"),
                })


        if is_sensitive_sink(e):

            counts[
                "heuristic_sink_keyword_matches"
            ] += 1

            if len(examples_sink) < 5:
                examples_sink.append({
                    "event_id":
                        e.get("event_id"),

                    "provider":
                        e.get("provider"),

                    "event_type":
                        e.get("event_type"),

                    "tool_name":
                        e.get("tool_name"),

                    "action_type":
                        e.get("action_type"),

                    "artifact":
                        e.get("artifact"),
                })


def rate(a, b):
    return (
        counts[a] / counts[b]
        if counts[b]
        else None
    )


summary = {
    "counts":
        dict(counts),

    "provider_events":
        dict(providers),

    "coverage": {
        "tool_call_action_type_rate":
            rate(
                "tool_calls_with_action_type",
                "tool_calls",
            ),

        "tool_call_tool_name_rate":
            rate(
                "tool_calls_with_tool_name",
                "tool_calls",
            ),

        "tool_call_id_rate":
            rate(
                "tool_calls_with_call_id",
                "tool_calls",
            ),

        "tool_result_parent_link_rate":
            rate(
                "tool_results_with_parent",
                "tool_results",
            ),
    },

    "examples": {
        "candidate_external_sources":
            examples_source,

        "candidate_sensitive_sinks":
            examples_sink,
    },

    "interpretation": (
        "The canonical schema preserves tool identity, semantic action "
        "labels, call identifiers, and call-result relationships needed "
        "for downstream safety enrichment. Keyword-based source/sink "
        "matches are illustrative probes only and are not validated "
        "safety labels or attack prevalence estimates."
    ),

}


OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUT.write_text(
    json.dumps(
        summary,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print(
    json.dumps(
        summary,
        indent=2,
        ensure_ascii=False,
    )
)
