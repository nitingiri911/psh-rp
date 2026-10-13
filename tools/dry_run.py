import random
import sys
import time
from engine import config as c
from engine.engine import Engine

if len(sys.argv) > 1:
    c.PROBE_INTERVAL = float(sys.argv[1])

N = {}


def fake(link):
    n = N[link] = N.get(link, 0) + 1
    lat = 10 + random.gauss(0, 1)
    jit = 1 + abs(random.gauss(0, 0.3))
    loss = 0.0
    if link == "r1-r2" and n > 40:
        k = min(1.0, (n - 40) / 25)
        lat += 190 * k
        jit += 45 * k
        loss = 60 * k
    if link == "r3-r4":
        jit += random.uniform(0, 40)
    return {"latency": lat, "jitter": jit, "loss": loss}


e = Engine(
    ["r1-r2", "r3-r4"],
    fake,
    lambda l, ts: print("AT_RISK", l, round(ts, 2)),
    lambda l, ts: print("HARD_CUTOFF", l, round(ts, 2)),
    lambda l, ts: print("CLEAR", l, round(ts, 2)),
    tag="dry",
)
e.start()
time.sleep(95 * c.PROBE_INTERVAL)
e.stop()
print(open("logs/dry_events.csv").read())
