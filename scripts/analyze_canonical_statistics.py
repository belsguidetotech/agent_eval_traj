import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np 
import pandas as pd 
import matplotlib.pyplot as plt 

EVENTS = Path("data/processed/canonical_events_v1.jsonl")
TRAJ = Path("results/statistics/canonical_trajectory_summary.csv")
RUNS = Path("results/statistics/run_summary.csv")
OUT_DIR = Path("results/statistics")
FIG_DIR = Path("results/figures")
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

traj = pd.read_csv(TRAJ)
events = []
with EVENTS.open() as f:
    for line in f:
        if line.strip():
            events.append(json.loads(line))
ev = pd.DataFrame(events)

def describe_numeric(series):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return {}
    return {
        "N": len(s),
        "mean": s.mean(),
        "median": s.median(),
        "p25": s.quantile(.25),
        "p75": s.quantile(.75),
        "p90": s.quantile(.90),
        "p95": s.quantile(.95),
        "min": s.min(),
        "max": s.max(),
    }
rows = []
for variable in [
    "n_raw_records",
    "n_canonical_events",
    "event_expansion_ratio",
]:
    stats = describe_numeric(traj[variable])
    rows.append({"scope": "all", "provider": "all", "variable": variable, **stats})
for provider, df in traj.groupby(
    "provider"
):
    for variable in [
        "n_raw_records",
        "n_canonical_events",
        "event_expansion_ratio",
    ]:
        stats = describe_numeric(df[variable])
        rows.append({"scope": "provider", "provider": provider, "variable": variable, **stats})
pd.DataFrame(rows).to_csv(OUT_DIR / "canonical_distribution_summary.csv", index=False)
event_type_summary = (ev.groupby(["provider", "event_type"]).size().reset_index(name="count"))
provider_totals = (event_type_summary.groupby("provider")["count"].transform("sum"))
event_type_summary["provider_fraction"] = (event_type_summary["count"] / provider_totals)
event_type_summary.to_csv(OUT_DIR / "canonical_event_type_summary.csv", index=False)
overall_event_types = (ev["event_type"].value_counts().rename_axis("event_type").reset_index(name="count"))
overall_event_types["fraction"] = overall_event_types["count"] / len(ev)
overall_event_types.to_csv(OUT_DIR / "canonical_event_type_overall.csv", index=False)
actions = (ev[ev["event_type"] == "tool_call"]["action_type"].fillna("unknown").value_counts().rename_axis("action_type").reset_index(name="count"))
actions["fraction"] = actions["count"] / actions["count"].sum()
actions.to_csv(OUT_DIR / "canonical_action_type_summary.csv", index=False)
stage_summary = (ev.groupby(["stage", "event_type"]).size().reset_index(name="count"))
stage_summary.to_csv(OUT_DIR / "canonical_stage_event_summary.csv", index=False)
provider_summary = (traj.groupby("provider").agg(trajectories=("trajectory_id", "nunique"),
                                                repositories=("repository_id", "nunique"),
                                                raw_records=("n_raw_records", "sum"),
                                                canonical_events=("n_canonical_events", "sum"),
                                                median_events=("n_canonical_events", "median"),
                                                ).reset_index())
provider_summary.to_csv(OUT_DIR / "canonical_provider_summary.csv", index=False)    
repo = (traj.groupby("repository_id").agg(provider_trajectories=("trajectory_id", "nunique"),
                                          raw_records=("n_raw_records", "sum"),
                                          canonical_events=("n_canonical_events", "sum"),
                                          ).reset_index())
repo["event_expansion_ratio"] = np.where(
    repo["raw_records"] > 0,
    repo["canonical_events"] / repo["raw_records"],
    np.nan,
) 
repo.to_csv(OUT_DIR / "canonical_repository_summary.csv", index=False)    
transition_counts = Counter()      
for trajectory_id, df in ev.groupby("trajectory_id"):
    df = df.sort_values("canonical_event_index")
    types = (df["event_type"].tolist())
    for a, b in zip(types, types[1:]):
        transition_counts[(a, b)] += 1
transition_rows =  [
    {
        "from_event": a,
        "to_event": b,
        "count": n,
    }
    for (a, b), n 
    in transition_counts.items()
]   
transitions = pd.DataFrame(transition_rows)
transitions = transitions.sort_values("count", ascending=False)
transitions.to_csv(OUT_DIR / "canonical_transition_summary.csv", index=False)
x = traj[traj["n_canonical_events"]>0]["n_canonical_events"]
plt.figure(figsize=(8,5))
plt.hist(x, bins=50)
plt.xlabel("Canonical events per provider trajectory")
plt.ylabel("Number of trajectories")
plt.title("Canonical trajectory length distribution")
plt.tight_layout()
plt.savefig(FIG_DIR / "canonical_event_count_hist.png", dpi=200)
plt.close()

plt.figure(figsize=(8,5))
plt.hist(np.log10(x), bins=50)
plt.xlabel("log10(canonical events)")
plt.ylabel("Number of trajectories")
plt.title("Canonical trajectory length (log scale)")
plt.tight_layout()
plt.savefig(FIG_DIR / "canonical_event_count_log_hist.png", dpi=200),
plt.close()

ratio = traj[
    np.isfinite(traj["event_expansion_ratio"])
]["event_expansion_ratio"]
plt.figure(figsize=(8,5))
plt.hist(ratio, bins=50)
plt.xlabel("Canonical events / raw JSON records")
plt.ylabel("Number of trajectories")
plt.title("Canonical event expansion ratio")
plt.tight_layout()
plt.savefig(FIG_DIR / "canonical_event_expansion_ratio_hist.png", dpi=200)
plt.close()

plot_df = traj[traj["n_raw_records"] > 0]
plt.figure(figsize=(7,6))
plt.scatter(plot_df["n_raw_records"], plot_df["n_canonical_events"], alpha=.35)
limit = max(plot_df["n_raw_records"].max(), plot_df["n_canonical_events"].max())
plt.plot([0, limit], [0, limit], linestyle="--")
plt.xlabel("Raw JSON records")
plt.ylabel("Canonical events")
plt.title("Raw records vs canonical events")
plt.tight_layout()
plt.savefig(FIG_DIR / "canonical_raw_vs_events.png", dpi=200)
plt.close()

plot_types = (overall_event_types.sort_values("count"))
plt.figure(figsize=(8,5))
plt.barh(plot_types["event_type"], plot_types["fraction"])
plt.xlabel("Fraction of canonical events")
plt.ylabel("Event type")
plt.title("Canonical event composition")
plt.tight_layout()
plt.savefig(FIG_DIR / "canonical_event_type_composition.png", dpi=200)
plt.close()

types = sorted(ev["event_type"].unique())
matrix = pd.DataFrame(0, index=types, columns=types, dtype=float)
for _, r in transitions.iterrows():
    matrix.loc[
        r["from_event"],
        r["to_event"],
    ] += r["count"]
row_sums = matrix.sum(axis=1)
normalized = matrix.div(row_sums.replace(0, np.nan),axis=0)
plt.figure(figsize=(8,7))
plt.imshow(normalized.values, aspect="auto")
plt.xticks(range(len(types)), types, rotation=45, ha="right")
plt.yticks(range(len(types)), types)
plt.xlabel("Next event")
plt.ylabel("Current event")
plt.title("Canonical event transition probabilities")
plt.colorbar(label="P(next event | current event)")
plt.tight_layout()
plt.savefig(FIG_DIR / "canonical_transition_matrix.png", dpi=200)
plt.close()

if RUNS.exists():
    runs = pd.read_csv(RUNS)
    repo_col = None
    for candidate in [
        "repo_name",
        "repository_id",
    ]:
        if candidate in runs.columns:
            repo_col = candidate
            break
    duration_col = None
    for candidate in [
        "run_duration_sec",
        "duration_sec",
        "total_duration_sec",
    ]:
        if candidate in runs.columns:
            duration_col = candidate
            break
    if (repo_col is not None and duration_col is not None):
        merged = repo.merge(
            runs[
                [
                    repo_col,
                    duration_col,
                ]
            ],
            left_on="repository_id",
            right_on=repo_col,
            how="inner",
        )
        merged.to_csv(
            OUT_DIR / 
            "canonical_timing_join.csv",
            index=False,
        )
        plt.figure(figsize=(7, 6))
        plt.scatter(merged["canonical_events"], merged[duration_col] / 60, alpha=.4)
        plt.xlabel("Canonical events")
        plt.ylabel("Run duration (minutes)")
        plt.title("Trajectory length vs run duration")
        plt.tight_layout()
        plt.savefig(FIG_DIR /
                    "canonical_events_vs_duration.png",
                    dpi=200,
        )
        plt.close()
print("\nCANONICAL STATISTICS COMPLETE")
print("--------------------------------")
print("Provider trajectories:",
      traj["trajectory_id"].nunique(),
)
print(
    "Repositories:",
    traj["repository_id"].nunique(),
)
print(
    "Canonical_events:",
    len(ev),
)
print("\nTrajectory event count:")
print(pd.Series(describe_numeric(traj["n_canonical_events"])))
print("\nEvent expansion ratio:")
print(pd.Series(describe_numeric(traj["event_expansion_ratio"])))
print("\nTop event transitions:")
print(transitions.head(20).to_string(index=False))
print("\nWrote statistics to:")
print(OUT_DIR)
print("\nWrote figures to:")
print(FIG_DIR)