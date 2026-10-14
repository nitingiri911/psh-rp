import csv
import sys
from engine import config as c


def load(path):
    try:
        with open(path) as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def show(x):
    return "-" if x is None else f"{x:.1f}"


def metrics(tag, interval=None):
    interval = interval or c.PROBE_INTERVAL
    ev = load(f"logs/{tag}_events.csv")
    tel = load(f"logs/{tag}_telemetry.csv")
    fl = load(f"logs/{tag}_failures.csv")
    if not tel:
        return None
    t0 = min(float(r["ts"]) for r in tel)
    warm_end = t0 + c.WARMUP * interval
    marks = {r["event"]: (float(r["ts"]), r["link"]) for r in fl}
    start = marks.get("ramp_start")
    cut = marks.get("cut")
    out = {}
    for v in sorted({r["variant"] for r in tel}):
        lead = None
        cutoff = None
        false = warm = 0
        for r in ev:
            if r["variant"] != v:
                continue
            ts = float(r["ts"])
            target = start is not None and cut is not None and r["link"] == cut[1] and ts >= start[0]
            if r["event"] == "at_risk":
                if target:
                    if lead is None:
                        lead = cut[0] - ts
                elif ts < warm_end:
                    warm += 1
                else:
                    false += 1
            elif r["event"] == "hard_cutoff" and target and cutoff is None:
                cutoff = cut[0] - ts
        out[v] = {"lead": lead, "cutoff": cutoff, "false": false, "warm": warm}
    return out


def summarize(tag, interval=None):
    m = metrics(tag, interval)
    if m is None:
        print("no telemetry found for", tag)
        return
    print(f"{'variant':10} {'lead_s':>8} {'cutoff_lead_s':>14} {'false':>6} {'warmup':>7}")
    for v, r in m.items():
        print(f"{v:10} {show(r['lead']):>8} {show(r['cutoff']):>14} {r['false']:>6} {r['warm']:>7}")


if __name__ == "__main__":
    summarize(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else None)
