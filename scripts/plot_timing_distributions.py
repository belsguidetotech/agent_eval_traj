import csv
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

RUN = Path("results/statistics/run_summary.csv")
STAGE = Path("results/statistics/stage_summary.csv")
OUT = Path("results/figures")
OUT.mkdir(parents=True, exist_ok=True)

runs = list(csv.DictReader(RUN.open()))
stages = list(csv.DictReader(STAGE.open()))


def numeric(rows, field, filter_fn=None):
    xs = []

    for r in rows:
        if filter_fn and not filter_fn(r):
            continue

        try:
            x = float(r[field])

            if np.isfinite(x) and x >= 0:
                xs.append(x)

        except Exception:
            pass

    return np.array(xs)


# --------------------------------------
# 1. Total run duration
# --------------------------------------

x = numeric(
    runs,
    "run_duration_sec"
) / 60

plt.figure(figsize=(7, 4.5))
plt.hist(x, bins=40)
plt.xlabel("Run duration (minutes)")
plt.ylabel("Number of runs")
plt.title("Distribution of Run Duration")
plt.tight_layout()
plt.savefig(
    OUT / "run_duration_hist.png",
    dpi=200
)
plt.close()


# --------------------------------------
# 2. Log-duration distribution
# Handles the extreme right tail.
# --------------------------------------

x = numeric(
    runs,
    "run_duration_sec"
)

x = x[x > 0]

plt.figure(figsize=(7, 4.5))
plt.hist(np.log10(x), bins=40)
plt.xlabel("log10(run duration in seconds)")
plt.ylabel("Number of runs")
plt.title("Run Duration on Log Scale")
plt.tight_layout()
plt.savefig(
    OUT / "run_duration_log_hist.png",
    dpi=200
)
plt.close()


# --------------------------------------
# 3. Stage durations
# --------------------------------------

for stage_name in [
    "resource_finder",
    "experiment_runner",
]:

    x = numeric(
        stages,
        "stage_duration_sec",
        lambda r:
            r["stage_name"] == stage_name
    ) / 60

    plt.figure(figsize=(7, 4.5))
    plt.hist(x, bins=40)
    plt.xlabel("Stage duration (minutes)")
    plt.ylabel("Number of stages")
    plt.title(
        f"{stage_name}: Duration Distribution"
    )
    plt.tight_layout()
    plt.savefig(
        OUT /
        f"{stage_name}_duration_hist.png",
        dpi=200
    )
    plt.close()


# --------------------------------------
# 4. ECDF of run duration
# Often more useful than histogram
# for heavy-tailed durations.
# --------------------------------------

x = np.sort(
    numeric(
        runs,
        "run_duration_sec"
    ) / 60
)

y = np.arange(1, len(x) + 1) / len(x)

plt.figure(figsize=(7, 4.5))
plt.plot(x, y)
plt.xlabel("Run duration (minutes)")
plt.ylabel("Fraction of runs ≤ duration")
plt.title("ECDF of Run Duration")
plt.tight_layout()
plt.savefig(
    OUT / "run_duration_ecdf.png",
    dpi=200
)
plt.close()


# --------------------------------------
# 5. Completed vs incomplete
# --------------------------------------

for status in ["True", "False"]:

    x = numeric(
        runs,
        "run_duration_sec",
        lambda r:
            r["pipeline_completed"] == status
    ) / 60

    print(
        status,
        "N =", len(x),
        "median_min =",
        np.median(x) if len(x) else None
    )


print("\nWrote figures to:", OUT)
