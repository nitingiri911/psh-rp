#!/usr/bin/env python3
"""
One failover run (Member 1): converge, send 100 packets/s h1 -> h2, kill a link,
measure convergence time and packets lost. Appends to logs/baseline_failover.csv
and logs/<tag>_failures.csv (ts,link,cut) for Nitin's engine.

    sudo python3 failover_test.py --proto ospf --timers default --mode blackhole --post 60
Use run_baseline.sh to repeat this for every protocol and timer setting.
"""
import argparse
import csv
import os
import sys
import time
from pathlib import Path

import netem_ctl
import psh_topo as T
from ping_analysis import analyze, parse_ping

LOGS = Path(__file__).resolve().parent.parent / "logs"
PING_FILE = "/tmp/pshrp_ping.txt"


def append_row(path, header, row):
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proto", choices=["ospf", "rip"], default="ospf")
    ap.add_argument("--timers", choices=["default", "tuned"], default="default")
    ap.add_argument("--link", default="r2-r6", help="link to kill, e.g. r2-r6")
    ap.add_argument("--mode", choices=["blackhole", "down"], default="blackhole",
                    help="blackhole = silent failure found by timers; down = interface goes down")
    ap.add_argument("--pre", type=float, default=5, help="seconds of traffic before the failure")
    ap.add_argument("--post", type=float, default=60, help="seconds of traffic after the failure")
    ap.add_argument("--settle", type=float, default=10, help="seconds to wait after first ping works")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    a, b = args.link.split("-")
    tag = args.tag or f"{args.proto}_{args.timers}_{args.mode}"
    LOGS.mkdir(exist_ok=True)

    net = T.build_net(2)
    net.start()
    T.set_ips(net)
    try:
        T.write_configs(args.proto, args.timers)
        T.start_frr(net, args.proto)
        t = T.wait_converged(net)
        if t is None:
            sys.exit("Network never converged, run aborted.")
        time.sleep(args.settle)

        count = int((args.pre + args.post) * 100)
        net["h1"].cmd(f"rm -f {PING_FILE}; ping -D -i 0.01 -W 1 -c {count} 192.168.2.10 > {PING_FILE} 2>&1 &")
        time.sleep(args.pre)
        t_cut = netem_ctl.cut(net, a, b) if args.mode == "down" else netem_ctl.blackhole(net, a, b)
        time.sleep(args.post + 2)
        net["h1"].cmd("pkill -INT ping")
        time.sleep(1)
        with open(PING_FILE) as f:
            text = f.read()
        (LOGS / "raw").mkdir(exist_ok=True)
        with open(LOGS / "raw" / f"{tag}_run{args.run}_ping.txt", "w") as g:
            g.write(text)
    finally:
        net.stop()
        T.stop_frr()

    res = analyze(parse_ping(text), t_cut)
    append_row(LOGS / "baseline_failover.csv",
               ["tag", "proto", "timers", "mode", "link", "run", "t_cut", "conv_time_s", "lost_packets", "recovered"],
               [tag, args.proto, args.timers, args.mode, args.link, args.run, f"{t_cut:.3f}",
                f"{res['conv_time']:.3f}", res["lost"], res["recovered"]])
    append_row(LOGS / f"{tag}_failures.csv", ["ts", "link", "cut"], [f"{t_cut:.3f}", args.link, 1])
    print(f"RESULT {tag} run {args.run}: convergence {res['conv_time']:.2f} s, "
          f"lost {res['lost']} packets, recovered={res['recovered']}")


if __name__ == "__main__":
    main()
