import csv
import glob
import os
import sys
from collections import defaultdict
from engine import config as c
from engine.detector import LinkDetector
from engine.scoring import LinkScorer
from tools.batch import stats

KEYS = ["FIXED_THRESHOLD", "SIGMA_K", "N_CONSEC", "ALPHA", "HARD_CUTOFF", "FREEZE_MODE"]


def load(tag):
    samples = defaultdict(list)
    with open(f"logs/{tag}_telemetry.csv") as f:
        for r in csv.DictReader(f):
            if r["variant"] == c.PRIMARY:
                samples[r["link"]].append(
                    (float(r["ts"]), float(r["latency"]), float(r["jitter"]), float(r["loss"]))
                )
    marks = {}
    try:
        with open(f"logs/{tag}_failures.csv") as f:
            for r in csv.DictReader(f):
                marks[r["event"]] = (float(r["ts"]), r["link"])
    except FileNotFoundError:
        pass
    return samples, marks


def load_set(prefix):
    paths = sorted(glob.glob(f"logs/{prefix}_[0-9][0-9]_telemetry.csv"))
    tags = [p[5:-14] for p in paths]
    return [load(t) for t in tags if os.path.exists(f"logs/{t}_done")]


def replay(samples, alpha, adaptive, hard):
    events = []
    on = tot = 0
    for link, rows in samples.items():
        sc = LinkScorer(alpha)
        det = LinkDetector(adaptive, hard)
        for ts, lat, jit, loss in rows:
            _, risk, evs = det.update(sc.update(lat, jit, loss))
            for e in evs:
                events.append((ts, link, e, det.seen))
            if det.seen > c.WARMUP:
                tot += 1
                on += int(risk)
    return events, 100.0 * on / max(1, tot)


def score(data, alpha, adaptive, hard):
    samples, marks = data
    start = marks.get("ramp_start")
    cut = marks.get("cut")
    lead = cutoff = None
    false = warm = 0
    events, risk_pct = replay(samples, alpha, adaptive, hard)
    for ts, link, e, seen in events:
        target = bool(start and cut) and link == cut[1] and ts >= start[0]
        if e == "at_risk":
            if target:
                if lead is None:
                    lead = cut[0] - ts
            elif seen <= c.WARMUP:
                warm += 1
            else:
                false += 1
        elif e == "hard_cutoff" and target and cutoff is None:
            cutoff = cut[0] - ts
    return lead, cutoff, false, warm, risk_pct


def pm(values, places=1):
    n, m, sd, ci = stats(values)
    if m is None:
        return "-"
    if ci is None:
        return f"{m:.{places}f}"
    return f"{m:.{places}f}+-{ci:.{places}f}"


def sweep(name, values, apply, noise_runs, ramp_runs):
    print(f"\n{name}")
    print(f"{'value':>10} {'lead_s':>14} {'cutoff_s':>14} {'false/run':>14} {'warmup/run':>14} {'alarm_%':>9}")
    for v in values:
        saved = {k: getattr(c, k) for k in KEYS}
        alpha, adaptive, hard = apply(v)
        leads, cutoffs, falses, warms, risks = [], [], [], [], []
        for d in ramp_runs:
            lead, cutoff, _, _, _ = score(d, alpha, adaptive, hard)
            if lead is not None:
                leads.append(lead)
            if cutoff is not None:
                cutoffs.append(cutoff)
        for d in noise_runs:
            _, _, f, w, r = score(d, alpha, adaptive, hard)
            falses.append(f)
            warms.append(w)
            risks.append(r)
        for k, val in saved.items():
            setattr(c, k, val)
        print(f"{str(v):>10} {pm(leads):>14} {pm(cutoffs):>14} {pm(falses, 2):>14} {pm(warms, 2):>14} {pm(risks):>9}")


def set_and_return(attr, adaptive, hard):
    def apply(v):
        setattr(c, attr, v)
        return c.ALPHA, adaptive, hard
    return apply


def main():
    noise = load_set(sys.argv[1])
    ramp = load_set(sys.argv[2])
    print(f"noise runs: {len(noise)}  ramp runs: {len(ramp)}")
    if not noise or not ramp:
        sys.exit("no finished runs found for one of the prefixes")
    sweep("fixed threshold (no adaptive, no hard cutoff)", [70, 75, 80, 85, 90, 95],
          set_and_return("FIXED_THRESHOLD", False, False), noise, ramp)
    sweep("adaptive: sigma multiplier k", [1.5, 2.0, 2.5, 3.0],
          set_and_return("SIGMA_K", True, True), noise, ramp)
    sweep("adaptive: consecutive samples N", [2, 3, 4, 5],
          set_and_return("N_CONSEC", True, True), noise, ramp)
    sweep("adaptive: trend weight alpha", [0.0, 1.0, 2.0, 4.0],
          lambda v: (v, True, True), noise, ramp)
    sweep("adaptive: hard cutoff", [20, 30, 40, 50],
          set_and_return("HARD_CUTOFF", True, True), noise, ramp)
    sweep("adaptive: baseline freeze mode", ["alert", "below", "none"],
          set_and_return("FREEZE_MODE", True, True), noise, ramp)


if __name__ == "__main__":
    main()
