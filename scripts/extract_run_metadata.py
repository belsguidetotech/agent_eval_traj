from pathlib import Path
import subprocess
import csv
import json

ROOT = Path("data/cache/repo_metadata")
MANIFEST = Path("manifests/hypogenic_repos.json")
OUT = Path("results/reconnaissance/run_metadata.csv")

repos = json.load(open(MANIFEST))

def git_show(repo, path):
    p = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{path}"],
        capture_output=True,
        text=True,
    )

    if p.returncode != 0:
        return None

    return p.stdout


rows = []

for meta in repos:

    name = meta["name"]
    repo = ROOT / name

    state = None
    raw = git_show(
        repo,
        ".neurico/pipeline_state.json"
    )

    if raw:
        try:
            state = json.loads(raw)
        except Exception:
            state = None

    if state:
        run_created = state.get("created_at")
        run_completed = state.get("completed_at")
        completed = state.get("completed")
        stages = list(
            state.get("stages", {}).keys()
        )
    else:
        run_created = None
        run_completed = None
        completed = None
        stages = []

    rows.append({
        "repo_name": name,
        "repo_created_at": meta.get("created_at"),
        "repo_pushed_at": meta.get("pushed_at"),
        "has_pipeline_state": bool(state),
        "run_created_at": run_created,
        "run_completed_at": run_completed,
        "pipeline_completed": completed,
        "pipeline_stages": "|".join(stages),
    })


OUT.parent.mkdir(
    parents=True,
    exist_ok=True
)

with OUT.open("w", newline="") as f:

    w = csv.DictWriter(
        f,
        fieldnames=rows[0].keys()
    )

    w.writeheader()
    w.writerows(rows)


print("Wrote:", OUT)

print(
    "pipeline states:",
    sum(r["has_pipeline_state"] for r in rows)
)

print(
    "run timestamps:",
    sum(bool(r["run_created_at"]) for r in rows)
)
