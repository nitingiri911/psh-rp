import csv
import math
import random
import statistics
import sys
import time
import networkx as nx
from engine.detector import LinkDetector
from engine.scoring import LinkScorer
from routing.backup import backup_path


def make_graph(n):
    g = nx.connected_watts_strogatz_graph(n, 4, 0.3, seed=random.randint(0, 10**6))
    nx.set_edge_attributes(g, 1, "weight")
    return g


def ci95(xs):
    return 1.96 * statistics.stdev(xs) / math.sqrt(len(xs))


def compare(n, trials):
    limited, full, extra = [], [], []
    none_limited = none_full = 0
    for _ in range(trials):
        g = make_graph(n)
        src, dst = random.sample(list(g.nodes), 2)
        path = nx.shortest_path(g, src, dst)
        bad = random.choice(list(zip(path, path[1:])))
        t0 = time.perf_counter()
        a = backup_path(g, src, dst, bad, hops=3)
        limited.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        b = backup_path(g, src, dst, bad, hops=n)
        full.append((time.perf_counter() - t0) * 1000)
        none_limited += a is None
        none_full += b is None
        if a and b:
            extra.append(len(a) - len(b))
    return {
        "limited_ms": statistics.mean(limited), "limited_ci": ci95(limited),
        "full_ms": statistics.mean(full), "full_ci": ci95(full),
        "none_limited_pct": 100.0 * none_limited / trials,
        "none_full_pct": 100.0 * none_full / trials,
        "extra_hops": statistics.mean(extra) if extra else float("nan"),
    }


def scoring_cost(n, cycles=300):
    g = make_graph(n)
    state = [(LinkScorer(), LinkDetector(True, True)) for _ in g.edges]
    times = []
    for i in range(cycles):
        t0 = time.perf_counter()
        for sc, det in state:
            det.update(sc.update(10 + random.gauss(0, 1), 1.0, 0.0))
        if i >= 30:
            times.append((time.perf_counter() - t0) * 1000)
    return len(state), statistics.mean(times), ci95(times)


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    random.seed(1)
    header = ["nodes", "links", "limited_ms", "limited_ci", "full_ms", "full_ci",
              "none_limited_pct", "none_full_pct", "extra_hops", "score_cycle_ms", "score_cycle_ci",
              "score_cpu_pct_of_1s"]
    rows = []
    for n in (10, 25, 50):
        c = compare(n, trials)
        links, sm, sci = scoring_cost(n)
        rows.append([n, links, c["limited_ms"], c["limited_ci"], c["full_ms"], c["full_ci"],
                     c["none_limited_pct"], c["none_full_pct"], c["extra_hops"], sm, sci, sm / 10.0])
        print(f"{n} nodes, {links} links: backup 3-hop {c['limited_ms']:.3f}+-{c['limited_ci']:.3f} ms, "
              f"full {c['full_ms']:.3f}+-{c['full_ci']:.3f} ms, none 3-hop {c['none_limited_pct']:.1f}% "
              f"full {c['none_full_pct']:.1f}%, extra hops {c['extra_hops']:.2f}, "
              f"scoring one cycle {sm:.3f}+-{sci:.3f} ms ({sm / 10.0:.2f}% of 1 s)")
    with open("results/scalability_extra.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows([[f"{x:.4f}" if isinstance(x, float) else x for x in r] for r in rows])


if __name__ == "__main__":
    main()
