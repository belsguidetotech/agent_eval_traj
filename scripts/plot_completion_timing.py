import csv
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

RUN = Path("results/statistics/run_summary.csv")
OUT = Path("results/figures")
OUT.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader(RUN.open()))

def durations(status):
    xs = []

    for r in rows:
        if r["pipeline_completed"] != status:
            continue

        try:
            x = float(r["run_duration_sec"]) / 60
            if np.isfinite(x) and x >= 0:
                xs.append(x)
        except:
            pass

    return np.array(xs)


for status, label in [
    ("True", "completed"),
    ("False", "incomplete"),
]:

    x = durations(status)

    plt.figure(figsize=(7, 4.5))
    plt.hist(x, bins=30)
    plt.xlabel("Run duration (minutes)")
    plt.ylabel("Number of runs")
    plt.title(
        f"Run Duration: {label.capitalize()} Runs (N={len(x)})"
    )
    plt.tight_layout()
    plt.savefig(
        OUT / f"run_duration_{label}_hist.png",
        dpi=200
    )
    plt.close()

    print(
        label,
        "N =", len(x),
        "median =", np.median(x),
        "p25 =", np.percentile(x, 25),
        "p75 =", np.percentile(x, 75),
    )

print("Wrote figures to", OUT)
