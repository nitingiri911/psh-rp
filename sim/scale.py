import csv, time, random, statistics, math
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from routing.backup import backup_path

def run(sizes=(10, 25, 50), trials=200, seed=1):
    random.seed(seed)
    rows = []
    for n in sizes:
        times = []
        while len(times) < trials:
            g = nx.connected_watts_strogatz_graph(n, 4, 0.3, seed=random.randint(0, 10**6))
            nx.set_edge_attributes(g, 1, "weight")
            src, dst = random.sample(list(g.nodes), 2)
            path = nx.shortest_path(g, src, dst)
            if len(path) < 2:
                continue
            bad = random.choice(list(zip(path, path[1:])))
            t0 = time.perf_counter()
            backup_path(g, src, dst, bad, hops=3)
            times.append((time.perf_counter() - t0) * 1000)
        m, s = statistics.mean(times), statistics.stdev(times)
        ci = 1.96 * s / math.sqrt(len(times))
        rows.append((n, trials, m, s, ci))
        print(f"{n} nodes: {m:.3f} ms +/- {ci:.3f} (95% CI)")
    with open("results/scalability.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["nodes", "trials", "mean_ms", "std_ms", "ci95_ms"])
        w.writerows(rows)
    plt.errorbar([r[0] for r in rows], [r[2] for r in rows],
                 yerr=[r[4] for r in rows], marker="o", capsize=4)
    plt.xlabel("Nodes"); plt.ylabel("Backup computation time (ms)")
    plt.title("PSH-RP backup computation vs network size")
    plt.savefig("results/scalability.png", dpi=150)

if __name__ == "__main__":
    run()