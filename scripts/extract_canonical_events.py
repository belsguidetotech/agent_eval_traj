import csv
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/cache/repo_metadata")
INVENTORY = Path("results/reconnaissance/runtime_trace_inventory.csv")

OUT_EVENTS = Path("data/processed/canonical_events_v1.jsonl")
OUT_TRAJ = Path("results/statistics/canonical_trajectory_summary.csv")
OUT_QC = Path("results/statistics/canonical_extraction_qc.csv")

SCHEMA_VERSION = "event_schema_v1"

STAGE_ORDER = {
    "resource_finder": 0,
    "execution": 1,
    "paper_writer": 2,
    "other": 99,
}


# ============================================================
# Git / path helpers
# ============================================================

def git_paths(repo: Path):
    p = subprocess.run(
        [
            "git", "-C", str(repo),
            "ls-tree", "-r", "--name-only", "HEAD",
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        return []
    return [x.strip() for x in p.stdout.splitlines() if x.strip()]


def git_show(repo: Path, path: str):
    p = subprocess.run(
        [
            "git", "-C", str(repo),
            "show", f"HEAD:{path}",
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        return None
    return p.stdout


def provider_from_path(path: str):
    name = Path(path).name.lower()
    m = re.search(
        r"_(claude|codex|gemini)_transcript\.jsonl$",
        name,
    )
    return m.group(1) if m else "unknown"


def stage_from_path(path: str):
    name = Path(path).name.lower()

    if "resource_finder" in name:
        return "resource_finder"
    if "execution" in name or "experiment" in name:
        return "execution"
    if "paper_writer" in name:
        return "paper_writer"
    return "other"


# ============================================================
# Generic value helpers
# ============================================================

def parse_timestamp(value):
    """Parse an ISO timestamp. Naive values are treated as UTC for ordering."""
    if not value:
        return None

    try:
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def json_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )
    except Exception:
        return str(value)


def detect_action_type(tool_name, payload=None):
    """
    Coarse, provider-independent action taxonomy.

    Prefer the tool name itself. Only use a few structural payload keys
    as fallback so arbitrary prompt/file content does not drive the label.
    """
    name = str(tool_name or "").lower()
    payload = payload if isinstance(payload, dict) else {}

    if any(x in name for x in ("search", "google", "find_papers", "websearch")):
        return "search"

    if any(x in name for x in ("read", "fetch", "open_file", "view_file")):
        return "read"

    if any(x in name for x in ("write", "create_file", "save_file")):
        return "write"

    if any(x in name for x in ("edit", "replace", "patch")):
        return "edit"

    if any(x in name for x in ("bash", "shell", "terminal", "python", "execute", "command")):
        return "execute"

    if any(x in name for x in ("inspect", "list", "glob", "grep")):
        return "inspect"

    keys = {str(k).lower() for k in payload.keys()}

    if "command" in keys:
        return "execute"

    if (
        {"query", "search_query", "search_term"} & keys
        or "queries" in keys
    ):
        return "search"

    if (
        ("content" in keys or "text" in keys)
        and ({"file_path", "filepath", "path"} & keys)
    ):
        return "write"

    if {"file_path", "filepath"} & keys:
        return "read"

    return "other"


def detect_artifact(payload):
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get("file_path"),
        payload.get("filepath"),
        payload.get("path"),
        payload.get("output_file"),
    ]

    file_obj = payload.get("file")
    if isinstance(file_obj, dict):
        candidates.extend(
            [
                file_obj.get("filePath"),
                file_obj.get("file_path"),
                file_obj.get("path"),
            ]
        )

    for value in candidates:
        if value:
            return str(value)

    return None


def status_is_error(status):
    return str(status or "").lower() in {
        "error",
        "failed",
        "failure",
        "cancelled",
        "canceled",
    }


# ============================================================
# Canonical event constructor
# ============================================================

def make_event(
    ctx,
    raw_index,
    sub_index,
    *,
    timestamp=None,
    actor=None,
    event_type="other",
    action_type=None,
    tool_name=None,
    action=None,
    observation=None,
    artifact=None,
    parent_event_id=None,
    tool_call_id=None,
    status=None,
    error_type=None,
    raw_type=None,
    raw_role=None,
    raw_uuid=None,
):
    transcript_id = ctx["path"].replace("/", "~")

    event_id = (
        f"{ctx['trajectory_id']}"
        f"::{ctx['stage']}"
        f"::{transcript_id}"
        f"::{raw_index}"
        f"::{sub_index}"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "repository_id": ctx["repo_name"],
        "trajectory_id": ctx["trajectory_id"],
        "provider": ctx["provider"],
        "stage": ctx["stage"],
        "stage_index": STAGE_ORDER.get(ctx["stage"], 99),
        "transcript_path": ctx["path"],
        "raw_record_index": raw_index,
        "raw_sub_event_index": sub_index,
        "canonical_event_index": None,
        "event_id": event_id,
        "timestamp": timestamp,
        "relative_time_sec": None,
        "actor": actor,
        "event_type": event_type,
        "action_type": action_type,
        "tool_name": tool_name,
        "action": action,
        "observation": observation,
        "artifact": artifact,
        "parent_event_id": parent_event_id,
        "tool_call_id": tool_call_id,
        "status": status,
        "error_type": error_type,
        "raw_type": raw_type,
        "raw_role": raw_role,
        "raw_uuid": raw_uuid,
    }


# ============================================================
# Claude adapter
# ============================================================

def parse_claude_record(record, raw_index, ctx, tool_map, unknown):
    events = []

    raw_type = str(record.get("type", ""))
    raw_uuid = record.get("uuid")
    timestamp = record.get("timestamp")

    # Assistant record: text/reasoning blocks and tool calls can coexist.
    if raw_type == "assistant":
        msg = record.get("message")

        if not isinstance(msg, dict):
            unknown[f"claude:{raw_type}:no_message"] += 1
            return [
                make_event(
                    ctx,
                    raw_index,
                    0,
                    timestamp=timestamp,
                    actor="assistant",
                    event_type="other",
                    action=json_text(record),
                    raw_type=raw_type,
                    raw_uuid=raw_uuid,
                )
            ]

        role = msg.get("role", "assistant")
        content = msg.get("content", [])

        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        elif not isinstance(content, list):
            content = [content]

        for j, block in enumerate(content):
            if not isinstance(block, dict):
                unknown["claude:assistant_block:non_dict"] += 1
                events.append(
                    make_event(
                        ctx,
                        raw_index,
                        j,
                        timestamp=timestamp,
                        actor=role,
                        event_type="other",
                        action=json_text(block),
                        raw_type=raw_type,
                        raw_role=role,
                        raw_uuid=raw_uuid,
                    )
                )
                continue

            btype = str(block.get("type", "")).lower()

            if btype in {"text", "thinking", "reasoning"}:
                text = (
                    block.get("text")
                    or block.get("thinking")
                    or block.get("content")
                )

                if text:
                    events.append(
                        make_event(
                            ctx,
                            raw_index,
                            j,
                            timestamp=timestamp,
                            actor=role,
                            event_type="message",
                            action_type=(
                                "reasoning"
                                if btype in {"thinking", "reasoning"}
                                else None
                            ),
                            action=json_text(text),
                            raw_type=raw_type,
                            raw_role=role,
                            raw_uuid=raw_uuid,
                        )
                    )

            elif btype == "tool_use":
                call_id = block.get("id")
                tool_name = block.get("name")
                payload = block.get("input", {})

                event = make_event(
                    ctx,
                    raw_index,
                    j,
                    timestamp=timestamp,
                    actor="assistant",
                    event_type="tool_call",
                    action_type=detect_action_type(tool_name, payload),
                    tool_name=tool_name,
                    action=json_text(payload),
                    artifact=detect_artifact(payload),
                    tool_call_id=call_id,
                    raw_type=raw_type,
                    raw_role=role,
                    raw_uuid=raw_uuid,
                )

                events.append(event)

                if call_id:
                    tool_map[str(call_id)] = event["event_id"]

            else:
                unknown[f"claude:assistant_block:{btype or '<empty>'}"] += 1
                events.append(
                    make_event(
                        ctx,
                        raw_index,
                        j,
                        timestamp=timestamp,
                        actor=role,
                        event_type="other",
                        action=json_text(block),
                        raw_type=raw_type,
                        raw_role=role,
                        raw_uuid=raw_uuid,
                    )
                )

        return events

    # User record: usually tool results, occasionally ordinary user text.
    if raw_type == "user":
        msg = record.get("message")

        role = "user"
        content = []

        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", [])

        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        elif not isinstance(content, list):
            content = [content]

        for j, block in enumerate(content):
            if not isinstance(block, dict):
                unknown["claude:user_block:non_dict"] += 1
                events.append(
                    make_event(
                        ctx,
                        raw_index,
                        j,
                        timestamp=timestamp,
                        actor=role,
                        event_type="other",
                        action=json_text(block),
                        raw_type=raw_type,
                        raw_role=role,
                        raw_uuid=raw_uuid,
                    )
                )
                continue

            btype = str(block.get("type", "")).lower()

            if btype == "tool_result":
                call_id = block.get("tool_use_id")
                structured = record.get("tool_use_result")

                structured_status = (
                    structured.get("status")
                    if isinstance(structured, dict)
                    else None
                )

                is_error = (
                    block.get("is_error") is True
                    or (
                        isinstance(structured, dict)
                        and structured.get("is_error") is True
                    )
                    or status_is_error(structured_status)
                )

                events.append(
                    make_event(
                        ctx,
                        raw_index,
                        j,
                        timestamp=timestamp,
                        actor="tool",
                        event_type="error" if is_error else "tool_result",
                        observation=json_text(block.get("content")),
                        artifact=detect_artifact(structured),
                        parent_event_id=tool_map.get(str(call_id)),
                        tool_call_id=call_id,
                        status="error" if is_error else (structured_status or "completed"),
                        error_type="tool_error" if is_error else None,
                        raw_type=raw_type,
                        raw_role=role,
                        raw_uuid=raw_uuid,
                    )
                )

            elif btype == "text":
                text = block.get("text")

                if text:
                    events.append(
                        make_event(
                            ctx,
                            raw_index,
                            j,
                            timestamp=timestamp,
                            actor=role,
                            event_type="message",
                            action=text,
                            raw_type=raw_type,
                            raw_role=role,
                            raw_uuid=raw_uuid,
                        )
                    )

            else:
                unknown[f"claude:user_block:{btype or '<empty>'}"] += 1
                events.append(
                    make_event(
                        ctx,
                        raw_index,
                        j,
                        timestamp=timestamp,
                        actor=role,
                        event_type="other",
                        action=json_text(block),
                        raw_type=raw_type,
                        raw_role=role,
                        raw_uuid=raw_uuid,
                    )
                )

        return events

    # Final CLI result.
    if raw_type == "result":
        is_error = record.get("is_error") is True

        return [
            make_event(
                ctx,
                raw_index,
                0,
                timestamp=timestamp,
                actor="system",
                event_type="error" if is_error else "status",
                observation=json_text(record.get("result")),
                status=(
                    "error"
                    if is_error
                    else record.get("subtype", "completed")
                ),
                error_type="run_error" if is_error else None,
                raw_type=raw_type,
                raw_uuid=raw_uuid,
            )
        ]

    # System/progress metadata.
    if raw_type in {"system", "tool_progress", "rate_limit_event"}:
        parent_tool = record.get("parent_tool_use_id")

        return [
            make_event(
                ctx,
                raw_index,
                0,
                timestamp=timestamp,
                actor="system",
                event_type="status",
                action=record.get("summary"),
                observation=record.get("status"),
                artifact=record.get("output_file"),
                parent_event_id=(
                    tool_map.get(str(parent_tool))
                    if parent_tool
                    else None
                ),
                tool_call_id=parent_tool,
                status=record.get("status") or record.get("subtype") or raw_type,
                raw_type=raw_type,
                raw_uuid=raw_uuid,
            )
        ]

    # Preserve unexpected Claude records rather than dropping them.
    unknown[f"claude:record:{raw_type or '<empty>'}"] += 1

    return [
        make_event(
            ctx,
            raw_index,
            0,
            timestamp=timestamp,
            actor="system",
            event_type="other",
            action=json_text(record),
            raw_type=raw_type,
            raw_uuid=raw_uuid,
        )
    ]


# ============================================================
# Gemini adapter
# ============================================================

def parse_gemini_record(record, raw_index, ctx, tool_map, unknown):
    raw_type = str(record.get("type", ""))
    timestamp = record.get("timestamp")

    if raw_type == "message":
        role = record.get("role", "assistant")

        return [
            make_event(
                ctx,
                raw_index,
                0,
                timestamp=timestamp,
                actor=role,
                event_type="message",
                action=record.get("content"),
                status="delta" if record.get("delta") else None,
                raw_type=raw_type,
                raw_role=role,
            )
        ]

    if raw_type == "tool_use":
        call_id = record.get("tool_id")
        tool_name = record.get("tool_name")
        payload = record.get("parameters", {})

        event = make_event(
            ctx,
            raw_index,
            0,
            timestamp=timestamp,
            actor="assistant",
            event_type="tool_call",
            action_type=detect_action_type(tool_name, payload),
            tool_name=tool_name,
            action=json_text(payload),
            artifact=detect_artifact(payload),
            tool_call_id=call_id,
            raw_type=raw_type,
        )

        if call_id:
            tool_map[str(call_id)] = event["event_id"]

        return [event]

    if raw_type == "tool_result":
        call_id = record.get("tool_id")
        status = record.get("status")
        is_error = status_is_error(status)

        return [
            make_event(
                ctx,
                raw_index,
                0,
                timestamp=timestamp,
                actor="tool",
                event_type="error" if is_error else "tool_result",
                observation=record.get("output"),
                parent_event_id=tool_map.get(str(call_id)),
                tool_call_id=call_id,
                status=status,
                error_type="tool_error" if is_error else None,
                raw_type=raw_type,
            )
        ]

    if raw_type == "error":
        return [
            make_event(
                ctx,
                raw_index,
                0,
                timestamp=timestamp,
                actor="system",
                event_type="error",
                observation=json_text(record),
                status="error",
                error_type=record.get("error_type", "runtime_error"),
                raw_type=raw_type,
            )
        ]

    if raw_type in {"init", "result"}:
        status = record.get("status") or raw_type
        is_error = status_is_error(status)

        return [
            make_event(
                ctx,
                raw_index,
                0,
                timestamp=timestamp,
                actor="system",
                event_type="error" if is_error else "status",
                observation=json_text(record.get("stats")),
                status=status,
                error_type="run_error" if is_error else None,
                raw_type=raw_type,
            )
        ]

    unknown[f"gemini:record:{raw_type or '<empty>'}"] += 1

    return [
        make_event(
            ctx,
            raw_index,
            0,
            timestamp=timestamp,
            actor="system",
            event_type="other",
            action=json_text(record),
            raw_type=raw_type,
        )
    ]


# ============================================================
# Codex adapter
# ============================================================

def parse_codex_record(
    record,
    raw_index,
    ctx,
    tool_map,
    completed_ids,
    unknown,
):
    events = []
    raw_type = str(record.get("type", ""))

    # Lifecycle wrapper records.
    if raw_type in {
        "thread.started",
        "turn.started",
        "turn.completed",
    }:
        return [
            make_event(
                ctx,
                raw_index,
                0,
                actor="system",
                event_type="status",
                status=raw_type,
                observation=json_text(record.get("usage")),
                raw_type=raw_type,
            )
        ]

    if raw_type not in {
        "item.started",
        "item.updated",
        "item.completed",
    }:
        unknown[f"codex:record:{raw_type or '<empty>'}"] += 1
        return [
            make_event(
                ctx,
                raw_index,
                0,
                actor="system",
                event_type="other",
                action=json_text(record),
                raw_type=raw_type,
            )
        ]

    item = record.get("item")

    if not isinstance(item, dict):
        unknown[f"codex:{raw_type}:no_item"] += 1
        return [
            make_event(
                ctx,
                raw_index,
                0,
                actor="assistant",
                event_type="other",
                action=json_text(record),
                raw_type=raw_type,
            )
        ]

    item_id = item.get("id")
    item_type = str(item.get("type", "")).lower()

    # If a completed record exists, do not double-count the started record.
    if raw_type == "item.started" and item_id in completed_ids:
        return events

    # Streaming/update metadata.
    if raw_type == "item.updated":
        return [
            make_event(
                ctx,
                raw_index,
                0,
                actor="system",
                event_type="status",
                action=json_text(item.get("items")),
                status="updated",
                tool_call_id=item_id,
                raw_type=raw_type,
            )
        ]

    # Command execution.
    if (
        "command" in item_type
        or "shell" in item_type
        or "execution" in item_type
        or item.get("command") is not None
    ):
        command = item.get("command")

        call = make_event(
            ctx,
            raw_index,
            0,
            actor="assistant",
            event_type="tool_call",
            action_type="execute",
            tool_name="shell",
            action=command,
            tool_call_id=item_id,
            status=item.get("status"),
            raw_type=raw_type,
        )

        events.append(call)

        if item_id:
            tool_map[str(item_id)] = call["event_id"]

        if raw_type == "item.completed":
            exit_code = item.get("exit_code")
            is_error = (
                exit_code not in (None, 0)
                or status_is_error(item.get("status"))
            )

            events.append(
                make_event(
                    ctx,
                    raw_index,
                    1,
                    actor="tool",
                    event_type="error" if is_error else "tool_result",
                    observation=item.get("aggregated_output"),
                    parent_event_id=call["event_id"],
                    tool_call_id=item_id,
                    status=item.get("status"),
                    error_type="nonzero_exit" if is_error else None,
                    raw_type=raw_type,
                )
            )

        return events

    # Text / analysis / reasoning items.
    if (
        item.get("text") is not None
        or any(
            x in item_type
            for x in ("message", "reason", "analysis")
        )
    ):
        return [
            make_event(
                ctx,
                raw_index,
                0,
                actor="assistant",
                event_type="message",
                action_type=(
                    "reasoning"
                    if any(x in item_type for x in ("reason", "analysis"))
                    else None
                ),
                action=item.get("text"),
                status=(
                    "completed"
                    if raw_type == "item.completed"
                    else "started"
                ),
                tool_call_id=item_id,
                raw_type=raw_type,
            )
        ]

    # Explicit file changes.
    if any(x in item_type for x in ("file", "patch", "edit")):
        return [
            make_event(
                ctx,
                raw_index,
                0,
                actor="assistant",
                event_type="artifact_change",
                action_type="edit",
                action=json_text(item),
                artifact=item.get("path") or item.get("file_path"),
                status=item.get("status"),
                tool_call_id=item_id,
                raw_type=raw_type,
            )
        ]

    # Todo / plan changes.
    if (
        "todo" in item_type
        or "plan" in item_type
        or item.get("items") is not None
    ):
        return [
            make_event(
                ctx,
                raw_index,
                0,
                actor="assistant",
                event_type="status",
                action=json_text(item.get("items")),
                status="plan_update",
                tool_call_id=item_id,
                raw_type=raw_type,
            )
        ]

    # Preserve unknown Codex item types for QC.
    unknown[f"codex:item:{item_type or '<empty>'}"] += 1

    return [
        make_event(
            ctx,
            raw_index,
            0,
            actor="assistant",
            event_type="other",
            action=json_text(item),
            tool_call_id=item_id,
            raw_type=raw_type,
        )
    ]


# ============================================================
# Single transcript parser
# ============================================================

def parse_transcript(repo_name, path):
    provider = provider_from_path(path)
    stage = stage_from_path(path)
    trajectory_id = f"{repo_name}::{provider}"

    ctx = {
        "repo_name": repo_name,
        "provider": provider,
        "trajectory_id": trajectory_id,
        "stage": stage,
        "path": path,
    }

    text = git_show(ROOT / repo_name, path)

    qc = {
        "repo_name": repo_name,
        "trajectory_id": trajectory_id,
        "provider": provider,
        "stage": stage,
        "transcript_path": path,
        "n_nonempty_lines": 0,
        "n_json_records": 0,
        "n_non_json_lines": 0,
        "n_canonical_events": 0,
        "n_unknown_structures": 0,
        "n_parse_exceptions": 0,
        "empty_transcript": False,
        "read_failed": False,
        "non_json_examples": "",
        "parse_exception_examples": "",
        "unknown_structures": "",
    }

    if text is None:
        qc["read_failed"] = True
        return [], qc

    records = []
    non_json_examples = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        qc["n_nonempty_lines"] += 1

        try:
            obj = json.loads(line)
            records.append(obj)
        except json.JSONDecodeError:
            qc["n_non_json_lines"] += 1

            if len(non_json_examples) < 3:
                non_json_examples.append(
                    f"line {line_no}: {line[:120]!r}"
                )

    qc["non_json_examples"] = " || ".join(non_json_examples)
    qc["n_json_records"] = len(records)

    if not records:
        qc["empty_transcript"] = True
        return [], qc

    tool_map = {}
    unknown = Counter()
    completed_ids = set()

    if provider == "codex":
        for record in records:
            if (
                isinstance(record, dict)
                and record.get("type") == "item.completed"
            ):
                item = record.get("item")

                if isinstance(item, dict) and item.get("id"):
                    completed_ids.add(item["id"])

    events = []
    parse_exception_examples = []

    for raw_index, record in enumerate(records):
        if not isinstance(record, dict):
            unknown[f"{provider}:non_dict"] += 1

            events.append(
                make_event(
                    ctx,
                    raw_index,
                    0,
                    event_type="other",
                    action=json_text(record),
                    raw_type="<non_dict>",
                )
            )
            continue

        try:
            if provider == "claude":
                new_events = parse_claude_record(
                    record,
                    raw_index,
                    ctx,
                    tool_map,
                    unknown,
                )

            elif provider == "gemini":
                new_events = parse_gemini_record(
                    record,
                    raw_index,
                    ctx,
                    tool_map,
                    unknown,
                )

            elif provider == "codex":
                new_events = parse_codex_record(
                    record,
                    raw_index,
                    ctx,
                    tool_map,
                    completed_ids,
                    unknown,
                )

            else:
                unknown[f"unknown_provider:{provider}"] += 1

                new_events = [
                    make_event(
                        ctx,
                        raw_index,
                        0,
                        event_type="other",
                        action=json_text(record),
                        raw_type=record.get("type"),
                    )
                ]

        except Exception as exc:
            qc["n_parse_exceptions"] += 1

            key = (
                f"parse_exception:{provider}:"
                f"{record.get('type', '<empty>')}:"
                f"{type(exc).__name__}"
            )
            unknown[key] += 1

            if len(parse_exception_examples) < 3:
                parse_exception_examples.append(
                    f"raw_index={raw_index} {type(exc).__name__}: {exc}"
                )

            new_events = [
                make_event(
                    ctx,
                    raw_index,
                    0,
                    actor="system",
                    event_type="other",
                    action=json_text(record),
                    status="parse_exception",
                    error_type=type(exc).__name__,
                    raw_type=record.get("type"),
                )
            ]

        events.extend(new_events)

    qc["n_canonical_events"] = len(events)
    qc["n_unknown_structures"] = sum(unknown.values())
    qc["parse_exception_examples"] = " || ".join(parse_exception_examples)
    qc["unknown_structures"] = "|".join(
        f"{key}:{value}"
        for key, value in unknown.most_common()
    )

    return events, qc


# ============================================================
# Corpus inventory
# ============================================================

def build_transcript_groups():
    inventory = list(csv.DictReader(INVENTORY.open()))
    analysis_repos = sorted({row["repo_name"] for row in inventory})

    transcript_groups = defaultdict(list)
    transcript_file_count = 0

    for i, repo_name in enumerate(analysis_repos, start=1):
        paths = git_paths(ROOT / repo_name)

        transcripts = [
            path
            for path in paths
            if (
                path.lower().startswith("logs/")
                and Path(path).name.lower().endswith("_transcript.jsonl")
            )
        ]

        for path in transcripts:
            provider = provider_from_path(path)
            trajectory_id = f"{repo_name}::{provider}"

            transcript_groups[trajectory_id].append(
                (repo_name, path)
            )
            transcript_file_count += 1

        if i % 50 == 0:
            print(f"Inventoried {i}/{len(analysis_repos)} repositories")

    for trajectory_id in transcript_groups:
        transcript_groups[trajectory_id].sort(
            key=lambda x: (
                STAGE_ORDER.get(stage_from_path(x[1]), 99),
                x[1],
            )
        )

    return analysis_repos, transcript_groups, transcript_file_count


# ============================================================
# Main extraction
# ============================================================

def main():
    (
        analysis_repos,
        transcript_groups,
        transcript_file_count,
    ) = build_transcript_groups()

    print(f"\nAnalysis repositories: {len(analysis_repos)}")
    print(f"Provider trajectories with transcript files: {len(transcript_groups)}")
    print(f"Transcript files: {transcript_file_count}")

    OUT_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    OUT_TRAJ.parent.mkdir(parents=True, exist_ok=True)
    OUT_QC.parent.mkdir(parents=True, exist_ok=True)

    qc_rows = []
    trajectory_rows = []

    global_event_types = Counter()
    global_provider_events = Counter()

    total_raw_records = 0
    total_non_json_lines = 0
    total_canonical_events = 0

    repositories_with_transcripts = set()
    event_bearing_trajectories = 0

    with OUT_EVENTS.open("w", encoding="utf-8") as fout:
        for traj_index, trajectory_id in enumerate(
            sorted(transcript_groups),
            start=1,
        ):
            transcript_entries = transcript_groups[trajectory_id]

            trajectory_events = []
            trajectory_qcs = []

            for repo_name, path in transcript_entries:
                events, qc = parse_transcript(repo_name, path)

                trajectory_events.extend(events)
                trajectory_qcs.append(qc)
                qc_rows.append(qc)

                total_raw_records += qc["n_json_records"]
                total_non_json_lines += qc["n_non_json_lines"]

            # All entries in one group share repo/provider by construction.
            first_qc = trajectory_qcs[0]
            repository_id = first_qc["repo_name"]
            provider = first_qc["provider"]

            repositories_with_transcripts.add(repository_id)

            trajectory_events.sort(
                key=lambda event: (
                    event["stage_index"],
                    event["transcript_path"],
                    event["raw_record_index"],
                    event["raw_sub_event_index"],
                )
            )

            valid_times = []

            for event in trajectory_events:
                dt = parse_timestamp(event["timestamp"])
                if dt is not None:
                    valid_times.append(dt)

            t0 = min(valid_times) if valid_times else None

            for canonical_index, event in enumerate(trajectory_events):
                event["canonical_event_index"] = canonical_index

                dt = parse_timestamp(event["timestamp"])

                if dt is not None and t0 is not None:
                    event["relative_time_sec"] = (dt - t0).total_seconds()

                fout.write(
                    json.dumps(event, ensure_ascii=False) + "\n"
                )

                global_event_types[event["event_type"]] += 1
                global_provider_events[event["provider"]] += 1

            n_raw = sum(q["n_json_records"] for q in trajectory_qcs)
            n_events = len(trajectory_events)

            if n_events > 0:
                event_bearing_trajectories += 1

            event_types = Counter(
                event["event_type"]
                for event in trajectory_events
            )

            stages = sorted(
                {q["stage"] for q in trajectory_qcs},
                key=lambda stage: STAGE_ORDER.get(stage, 99),
            )

            trajectory_rows.append(
                {
                    "trajectory_id": trajectory_id,
                    "repository_id": repository_id,
                    "provider": provider,
                    "n_transcripts": len(trajectory_qcs),
                    "n_empty_transcripts": sum(
                        bool(q["empty_transcript"])
                        for q in trajectory_qcs
                    ),
                    "n_read_failed_transcripts": sum(
                        bool(q["read_failed"])
                        for q in trajectory_qcs
                    ),
                    "n_raw_records": n_raw,
                    "n_non_json_lines": sum(
                        q["n_non_json_lines"]
                        for q in trajectory_qcs
                    ),
                    "n_unknown_structures": sum(
                        q["n_unknown_structures"]
                        for q in trajectory_qcs
                    ),
                    "n_parse_exceptions": sum(
                        q["n_parse_exceptions"]
                        for q in trajectory_qcs
                    ),
                    "n_canonical_events": n_events,
                    "event_expansion_ratio": (
                        n_events / n_raw
                        if n_raw
                        else None
                    ),
                    "n_message": event_types["message"],
                    "n_tool_call": event_types["tool_call"],
                    "n_tool_result": event_types["tool_result"],
                    "n_artifact_change": event_types["artifact_change"],
                    "n_error": event_types["error"],
                    "n_status": event_types["status"],
                    "n_other": event_types["other"],
                    "stages": "|".join(stages),
                }
            )

            total_canonical_events += n_events

            if traj_index % 50 == 0:
                print(
                    f"Parsed {traj_index}/{len(transcript_groups)} "
                    f"provider trajectories"
                )

    if trajectory_rows:
        with OUT_TRAJ.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=trajectory_rows[0].keys(),
            )
            writer.writeheader()
            writer.writerows(trajectory_rows)

    if qc_rows:
        with OUT_QC.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=qc_rows[0].keys(),
            )
            writer.writeheader()
            writer.writerows(qc_rows)

    print("\nCANONICAL EXTRACTION")
    print("--------------------")
    print("Analysis repositories:", len(analysis_repos))
    print("Repositories with transcript files:", len(repositories_with_transcripts))
    print("Provider trajectories:", len(transcript_groups))
    print("Event-bearing trajectories:", event_bearing_trajectories)
    print("Transcript files:", len(qc_rows))
    print("Raw JSON records:", total_raw_records)
    print("Non-JSON lines:", total_non_json_lines)
    print("Canonical events:", total_canonical_events)

    print("\nEVENT TYPES")
    print("-----------")
    for key, value in global_event_types.most_common():
        print(f"{key:20s} {value:8d}")

    print("\nPROVIDER EVENT COUNTS")
    print("---------------------")
    for key, value in global_provider_events.most_common():
        print(f"{key:20s} {value:8d}")

    print("\nQC")
    print("--")
    print(
        "Read failures:",
        sum(bool(q["read_failed"]) for q in qc_rows),
    )
    print(
        "Empty transcripts:",
        sum(bool(q["empty_transcript"]) for q in qc_rows),
    )
    print(
        "Transcripts with unknown structures:",
        sum(bool(q["unknown_structures"]) for q in qc_rows),
    )
    print(
        "Unknown structure occurrences:",
        sum(q["n_unknown_structures"] for q in qc_rows),
    )
    print(
        "Parse exceptions:",
        sum(q["n_parse_exceptions"] for q in qc_rows),
    )

    print("\nWrote:")
    print(OUT_EVENTS)
    print(OUT_TRAJ)
    print(OUT_QC)


if __name__ == "__main__":
    main()
