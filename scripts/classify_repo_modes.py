from pathlib import Path
import subprocess
import csv
import json

ROOT = Path("data/cache/repo_metadata")
MANIFEST = Path("manifests/hypogenic_repos.json")
OUT = Path("results/reconnaissance/all_repo_mode_signals.csv")

repos = json.load(open(MANIFEST))

rows = []

def tree(repo_dir):
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return None

    return [
        x.strip()
        for x in result.stdout.splitlines()
        if x.strip()
    ]


for meta in repos:

    name = meta["name"]
    repo = ROOT / name

    # --------------------------------
    # repository validity
    # --------------------------------

    if not repo.exists():
        rows.append({
            "repo_name": name,
            "repo_status": "inaccessible",
            "mode": "unknown",
            "confidence": "low",
            "provider": "unknown",
            "n_files": 0,
            "has_pipeline_state": False,
            "has_standard_logs": False,
            "has_autoresearch": False,
            "has_hitl": False,
            "has_hitl_launch": False,
            "evidence": "metadata clone unavailable",
        })
        continue

    paths = tree(repo)

    if paths is None:
        rows.append({
            "repo_name": name,
            "repo_status": "empty",
            "mode": "unknown",
            "confidence": "low",
            "provider": "unknown",
            "n_files": 0,
            "has_pipeline_state": False,
            "has_standard_logs": False,
            "has_autoresearch": False,
            "has_hitl": False,
            "has_hitl_launch": False,
            "evidence": "no valid HEAD",
        })
        continue

    low = [p.lower() for p in paths]

    # --------------------------------
    # provider
    # --------------------------------

    provider = "unknown"

    if any("codex" in p for p in low) or name.endswith("-codex"):
        provider = "codex"

    elif any("claude" in p for p in low) or name.endswith("-claude"):
        provider = "claude"

    elif any("gemini" in p for p in low) or name.endswith("-gemini"):
        provider = "gemini"

    # --------------------------------
    # structural signals
    # --------------------------------

    has_pipeline = ".neurico/pipeline_state.json" in low

    has_standard_logs = any(
        p.startswith("logs/")
        and (
            "transcript" in p
            or "execution_" in p
        )
        for p in low
    )

    has_auto = any(
        (
            "experiment-autoresearch" in p
            or "autoresearch" in p
            or p.endswith("whiteboard.json")
        )
        for p in low
    )

    has_hitl = any(
        p.startswith(".neurico/hitl/")
        or "/hitl/" in p
        for p in low
    )

    has_hitl_launch = any(
        p == ".neurico/hitl/launch.json"
        or p.endswith("/.neurico/hitl/launch.json")
        for p in low
    )

    has_idea = ".neurico/idea.yaml" in low

    # --------------------------------
    # repo status
    # --------------------------------

    if has_pipeline or has_standard_logs or has_auto or has_hitl:
        repo_status = "executed"

    elif has_idea:
        repo_status = "initialized_only"

    elif len(paths) == 0:
        repo_status = "empty"

    else:
        repo_status = "unclassified_content"

    # --------------------------------
    # mode
    # priority matters:
    #
    # HITL > AutoResearch > Standard
    # --------------------------------

    if has_hitl:
        mode = "hitl"
        confidence = "high"
        evidence = "HITL runtime artifacts"

    elif has_auto:
        mode = "autoresearch"
        confidence = "high"
        evidence = "AutoResearch runtime artifacts"

    elif has_pipeline and has_standard_logs:
        mode = "standard"
        confidence = "medium"
        evidence = (
            "ordinary NeuriCo pipeline and execution logs; "
            "no AutoResearch/HITL artifacts"
        )

    else:
        mode = "unknown"
        confidence = "low"
        evidence = "insufficient runtime evidence"

    rows.append({
        "repo_name": name,
        "repo_status": repo_status,
        "mode": mode,
        "confidence": confidence,
        "provider": provider,
        "n_files": len(paths),
        "has_pipeline_state": has_pipeline,
        "has_standard_logs": has_standard_logs,
        "has_autoresearch": has_auto,
        "has_hitl": has_hitl,
        "has_hitl_launch": has_hitl_launch,
        "evidence": evidence,
    })


OUT.parent.mkdir(parents=True, exist_ok=True)

with OUT.open("w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=rows[0].keys(),
    )
    writer.writeheader()
    writer.writerows(rows)


# --------------------------------
# summary
# --------------------------------

from collections import Counter

print("\nRepository status")
print("-----------------")

for k, v in Counter(r["repo_status"] for r in rows).most_common():
    print(f"{k:25s} {v:5d}")

print("\nMode")
print("----")

for k, v in Counter(r["mode"] for r in rows).most_common():
    print(f"{k:25s} {v:5d}")

print("\nProvider")
print("--------")

for k, v in Counter(r["provider"] for r in rows).most_common():
    print(f"{k:25s} {v:5d}")

print(
    "\nWrote:",
    OUT
)
