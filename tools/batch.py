import argparse
import csv
import math
import os
import subprocess
import sys
from statistics import mean, stdev
from tools.summary import metrics

T95 = [None, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
       2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
       2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def tcrit(df):
    return T95[df] if df < len(T95) else 1.96


def stats(values):
    n = len(values)
    if n == 0:
        return n, None, None, None
    m = mean(values)
    if n == 1:
        return n, m, None, None
    sd = stdev(values)
    return n, m, sd, tcrit(n - 1) * sd / math.sqrt(n)


def fmt(x):
    return "" if x is None else f"{x:.2f}"


def aggregate(prefix, tags, interval=None):
    runs = [m for m in (metrics(t, interval) for t in tags) if m]
    if not runs:
        print("no finished runs found")
        return
    os.makedirs("results", exist_ok=True)
    path = f"results/{prefix}_summary.csv"
    print(f"{len(runs)} finished runs")
    print(f"{'variant':10} {'metric':8} {'n':>3} {'mean':>8} {'sd':>8} {'ci95':>8}")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "metric", "n", "mean", "sd", "ci95"])
        for v in sorted(runs[0]):
            for key in ("lead", "cutoff", "false", "warm"):
                vals = [r[v][key] for r in runs if v in r and r[v][key] is not None]
                n, m, sd, ci = stats(vals)
                w.writerow([v, key, n, fmt(m), fmt(sd), fmt(ci)])
                print(f"{v:10} {key:8} {n:>3} {fmt(m):>8} {fmt(sd):>8} {fmt(ci):>8}")
    print("saved", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--aggregate-only", action="store_true")
    args, extra = ap.parse_known_args()
    prefix = args.prefix or args.scenario
    tags = [f"{prefix}_{k:02d}" for k in range(1, args.runs + 1)]
    if not args.aggregate_only:
        if os.geteuid() != 0:
            sys.exit("Run with sudo.")
        for tag in tags:
            if os.path.exists(f"logs/{tag}_events.csv"):
                print("skip", tag)
                continue
            print("run", tag, flush=True)
            subprocess.run([sys.executable, "-m", "tools.run_live", "--scenario", args.scenario, "--tag", tag] + extra)
            subprocess.run(["mn", "-c"], capture_output=True)
    aggregate(prefix, tags)


if __name__ == "__main__":
    main()
