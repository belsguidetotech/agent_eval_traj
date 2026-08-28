import json
import csv
import subprocess
from pathlib import Path
from collections import Counter

ROOT = Path("data/cache/repo_metadata")
SAMPLES = Path("manifests/canonical_sample_repos.txt")
OUT = Path("results/reconnaissance/transcript_schema_audit.csv")

def git_paths(repo):
    p = subprocess.run(
        [
            "git", "-C", str(repo),
            "ls-tree", "-r",
            "--name-only", "HEAD"
        ],
        capture_output=True,
        text=True,
        check=True, 
    )
    return [x.strip() for x in p.stdout.splitlines() if x.strip()]

def read_git_file(repo, path):
    p = subprocess.run(
        [
            "git", "-C", str(repo), 
            "show", 
            f"HEAD:{path}"
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        return None 
    return p.stdout

samples = []
for line in SAMPLES.open():
    line = line.strip()
    if not line:
        continue
    repo, reason = line.split("\t", 1)
    samples.append((repo, reason))
rows = []
for repo_name, reason in samples:
    repo = ROOT / repo_name
    paths = git_paths(repo)
    transcripts = [
        p for p in paths
        if (
            p.lower().startswith("logs/")
            and Path(p).name.lower().endswith("_transcript.jsonl")
        )
    ]
    for path in transcripts:
        text = read_git_file(repo, path)
        if text is None:
            print(
                "[READ FAIL]",
                repo_name,
                path
            )
            continue
        records = []
        bad_json = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                bad_json += 1
        top_keys = Counter()
        types = Counter()
        roles = Counter()
        has_timestamp = 0
        has_uuid = 0
        has_parent_tool_use_id = 0
        has_tool_use_result = 0
        has_message = 0
        for r in records:
            if not isinstance(r, dict):
                continue
            top_keys.update(r.keys())
            if r.get("type") is not None:
                types[str(r["type"])] += 1
            if r.get("timestamp") is not None:
                has_timestamp += 1
            if r.get("uuid") is not None:
                has_uuid += 1
            if (r.get("parent_tool_use_id") is not None):
                has_parent_tool_use_id += 1
            if (r.get("tool_use_result") is not None):
                has_tool_use_result += 1
            msg = r.get("message")
            if isinstance(msg, dict):
                has_message += 1
                role = msg.get("role")
                if role is not None:
                    roles[str(role)] += 1
        lowname = Path(path).name.lower()
        if "resource_finder" in lowname:
            stage = "resource_finder"
        elif ("execution" in lowname or "experiment" in lowname):
            stage = "execution"
        elif "paper_writer" in lowname:
            stage = "paper_writer"
        else:
            stage = "other"
        rows.append({
            "repo_name": repo_name,
            "sample_reason": reason,
            "stage": stage,
            "transcript_path": path,
            "n_records": len(records),
            "bad_json_lines": bad_json,
            "record_types": "|".join(
                f"{k}:{v}" 
                for k, v 
                in types.most_common()
            ),
            "message_roles": "|".join(
                f"{k}:{v}" 
                for k, v 
                in roles.most_common()
            ),
            "top_level_keys": "|".join(
                k 
                for k, _ 
                in top_keys.most_common()
            ),
            "n_with_timestamp": has_timestamp,
            "n_with_uuid": has_uuid,
            "n_with_parent_tool_use_id": has_parent_tool_use_id,
            "n_with_tool_use_result": has_tool_use_result,
            "n_with_message": has_message,
            })
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
print("\nTRANSCRIPT SCHEMA AUDIT")
print("-------------------------")
for r in rows:
    print()
    print(
        r["repo_name"],
        "::",
        r["stage"]
    )
    print(
        " records:",
        r["n_records"]
    )
    print(
        " types:",
        r["record_types"]
    )
    print(
        " roles:",
        r["message_roles"]
    )
    print(
        " timestamp:",
        r["n_with_timestamp"]
    )
    print(
        " uuid:",
        r["n_with_uuid"]
    )
    print(
        " parent_tool:",
        r["n_with_parent_tool_use_id"]
    )
    print(
        " tool_result:",
        r["n_with_tool_use_result"]
    )

print("\nWrote:", OUT)