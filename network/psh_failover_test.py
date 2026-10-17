#!/usr/bin/env python3
"""
One failover run with a degrading link, with or without PSH-RP (Member 1).

Timeline: converge -> (start engine if --psh) -> 100 pings/s h1 -> h2 -> healthy for --baseline s
          -> link ramps up (delay, jitter, loss) for --ramp s -> link fails (blackhole or down)
          -> traffic continues for --post s.
Without --psh this is plain OSPF/RIP under the same degradation, which is the fair comparison.
With --psh, Nitin's engine watches every link. On a hard cutoff, the standby path (computed
with networkx, avoiding the at-risk link) is installed with real routes (route_install.py).

    sudo python3 psh_failover_test.py --proto ospf --timers tuned --psh --run 1
    sudo python3 psh_failover_test.py --proto ospf --timers tuned --run 1        # same, no PSH-RP
Results are appended to logs/psh_failover.csv.
"""
import argparse
import csv
import os
import random
import re
import sys
import threading
import time
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import netem_ctl
import psh_topo as T
import route_install as R
from ping_analysis import analyze, parse_ping

LOGS = ROOT / "logs"
PING_FILE = "/tmp/pshrp_psh_ping.txt"
SUMMARY = re.compile(r"(\d+) packets transmitted, (\d+) received")
SRC, DST = "r1", "r6"
FWD_PREFIX, REV_PREFIX = "192.168.2.0/24", "192.168.1.0/24"


def on_path(path, link):
    a, b = link.split("-")
    return any({x, y} == {a, b} for x, y in zip(path, path[1:]))


class Swapper:
    """Callbacks for the engine: prepare a standby at-risk, install it at hard cutoff."""

    def __init__(self, net):
        self.net = net
        self.G = nx.Graph()
        self.G.add_edges_from(T.LINKS)
        self.primary = nx.shortest_path(self.G, SRC, DST)
        self.standby = {}
        self.active = None
        self.events = []
        self.lock = threading.Lock()

    def _backup(self, link):
        a, b = link.split("-")
        H = self.G.copy()
        H.remove_edge(a, b)
        try:
            return nx.shortest_path(H, SRC, DST)
        except nx.NetworkXNoPath:
            return None

    def on_at_risk(self, link, ts):
        with self.lock:
            self.events.append((ts, link, "at_risk"))
            if on_path(self.primary, link) and link not in self.standby:
                self.standby[link] = self._backup(link)

    def on_hard_cutoff(self, link, ts):
        with self.lock:
            self.events.append((ts, link, "hard_cutoff"))
            if self.active or not on_path(self.primary, link):
                return  # already swapped, or the link is not on the flow's path
            path = self.standby.get(link) or self._backup(link)
            if path is None:
                return  # no alternative: fall back to OSPF/RIP
            errors = (R.install_path(self.net, path, FWD_PREFIX)
                      + R.install_path(self.net, path[::-1], REV_PREFIX))
            if not errors and R.route_dev(self.net, SRC, "192.168.2.10") != R.hop(path[0], path[1])[0]:
                errors.append("route check failed: traffic does not use the backup interface")
            if errors:
                print("SWAP FAILED:", errors, file=sys.stderr)
                R.remove_path(self.net, path, FWD_PREFIX)
                R.remove_path(self.net, path[::-1], REV_PREFIX)
                self.events.append((time.time(), link, "swap_failed"))
                return
            self.active = (link, path, time.time())
            self.events.append((self.active[2], link, "swap"))

    def on_clear(self, link, ts):
        with self.lock:
            self.events.append((ts, link, "clear"))
            if self.active and self.active[0] == link:
                R.remove_path(self.net, self.active[1], FWD_PREFIX)
                R.remove_path(self.net, self.active[1][::-1], REV_PREFIX)
                self.active = None
            self.standby.pop(link, None)

    def swap_ts(self):
        return self.active[2] if self.active else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proto", choices=["ospf", "rip"], default="ospf")
    ap.add_argument("--timers", choices=["default", "tuned"], default="tuned")
    ap.add_argument("--psh", action="store_true", help="run PSH-RP (engine + route swap)")
    ap.add_argument("--link", default="r1-r2")
    ap.add_argument("--failure", choices=["down", "blackhole"], default="blackhole")
    ap.add_argument("--baseline", type=float, default=45, help="healthy seconds before the ramp")
    ap.add_argument("--ramp", type=int, default=60, help="seconds of degradation before the failure (0 = sudden)")
    ap.add_argument("--post", type=float, default=30, help="seconds of traffic after the failure")
    ap.add_argument("--jitter", type=float, default=10,
                    help="random 0..N s added to --baseline, so the failure lands at a random point of the probe and hello cycles")
    ap.add_argument("--run", type=int, default=1)
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    os.chdir(ROOT)  # the engine writes logs/ relative to the current folder
    a, b = args.link.split("-")
    mode = "psh" if args.psh else "plain"
    tag = f"{mode}_{args.proto}_{args.timers}_{args.failure}_r{args.ramp}"
    LOGS.mkdir(exist_ok=True)

    net = T.build_net(2)
    net.start()
    T.set_ips(net)
    eng = None
    swapper = None
    try:
        T.write_configs(args.proto, args.timers)
        T.start_frr(net, args.proto)
        if T.wait_converged(net) is None:
            sys.exit("Network never converged, run aborted.")
        time.sleep(10)
        if args.psh:
            from engine.engine import Engine
            from engine.telemetry import make_probe_fn
            links = {f"{x}-{y}": (net[x], f"{x}-{y}", f"10.0.{i}.2") for i, (x, y) in enumerate(T.LINKS, 1)}
            swapper = Swapper(net)
            eng = Engine(links, make_probe_fn(links), swapper.on_at_risk, swapper.on_hard_cutoff,
                         swapper.on_clear, tag=f"{tag}_run{args.run}")
            eng.start()
        base = args.baseline + random.uniform(0, args.jitter)
        total = base + args.ramp + args.post
        net["h1"].cmd(f"rm -f {PING_FILE}; ping -D -i 0.01 -W 1 -c {int((total + 6) * 100)} 192.168.2.10 > {PING_FILE} 2>&1 &")
        time.sleep(base)
        t_ramp = time.time()
        if args.ramp > 0:
            netem_ctl.ramp(net, a, b, duration=args.ramp, steps=args.ramp, then_cut=False)
        t_fail = netem_ctl.cut(net, a, b) if args.failure == "down" else netem_ctl.blackhole(net, a, b)
        time.sleep(args.post)
        net["h1"].cmd("pkill -INT ping")
        time.sleep(2)
        with open(PING_FILE) as f:
            text = f.read()
    finally:
        if eng:
            eng.stop()
        net.stop()
        T.stop_frr()

    res = analyze(parse_ping(text), t_fail)
    m = SUMMARY.findall(text)
    lost_total = int(m[-1][0]) - int(m[-1][1]) if m else float("nan")
    swap = swapper.swap_ts() if swapper else None
    lead = (t_fail - swap) if swap else float("nan")
    path = LOGS / "psh_failover.csv"
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["tag", "proto", "timers", "psh", "failure", "link", "ramp_s", "run", "t_ramp", "t_fail",
                        "swap_lead_s", "outage_s", "lost_gap", "lost_total", "recovered", "baseline_s"])
        w.writerow([tag, args.proto, args.timers, args.psh, args.failure, args.link, args.ramp, args.run,
                    f"{t_ramp:.3f}", f"{t_fail:.3f}", f"{lead:.2f}", f"{res['conv_time']:.3f}",
                    res["lost"], lost_total, res["recovered"], f"{base:.2f}"])
    print(f"RESULT {tag} run {args.run}: swap {lead:.1f} s before the failure, outage {res['conv_time']:.2f} s, "
          f"lost {lost_total} packets in total, recovered={res['recovered']}")


if __name__ == "__main__":
    main()
