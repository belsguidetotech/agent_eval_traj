import csv
from collections import defaultdict
from pathlib import Path 
INV = Path("results/reconnaissance/runtime_trace_inventory.csv")
OUT = Path("manifests/canonical_sample_repos.txt")
rows = list(csv.DictReader(INV.open()))
selected = []
used = set()

def add(repo, reason):
    if repo in used:
        return
    used.add(repo)
    selected.append((repo, reason))

# normal two-stage trajectory for each provider
for provider in ["claude", "codex", "gemini"]:
    for r in rows:
        if (
            r["provider"] == provider
            and r["n_resource_transcripts"] == "1"
            and r["n_execution_transcripts"] == "1"
            and r["n_other_runtime_transcripts"] == "0"
        ):
            add(r["repo_name"],
                f"normal_{provider}")
            break

# multi-provider
for r in rows:
    if (int(r["n_resource_transcripts"]) == 2
        and int(r["n_execution_transcripts"]) == 2):
        add(r["repo_name"], "multi_provider")
        break

# paper writer
for r in rows:
    if int(r["n_other_runtime_transcripts"]) > 0:
        add(r["repo_name"], "paper_writer")
        break

# resource only
for r in rows:
    if (int(r["n_resource_transcripts"])>0
        and int(r["n_execution_transcripts"]) == 0):
        add(r["repo_name"], "resource_only")
        break

# execution only 
for r in rows:
    if (int(r["n_resource_transcripts"]) == 0
        and int(r["n_execution_transcripts"]) > 0):
        add(r["repo_name"], "execution_only")
        break


# additional normal trajectories
for r in rows:
    if len(selected) >= 10:
        break
    if (r["n_resource_transcripts"] == "1" 
        and r["n_execution_transcripts"] == "1"):
        add(r["repo_name"], "additional_normal")

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w") as f:
    for repo, reason in selected:
        f.write(f"{repo}\t{reason}\n")
print("canonical sample")
print("-----------------")
for repo, reason in selected:
    print(f"{reason:25s} {repo}")
print("\nN =", len(selected))
print("Wrote:", OUT)
