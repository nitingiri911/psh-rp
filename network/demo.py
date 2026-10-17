#!/usr/bin/env python3
"""
Live demo (Member 1): the same degrading link, first with plain OSPF, then with PSH-RP.

    sudo python3 network/demo.py              # both phases, about 4 minutes
    sudo python3 network/demo.py --only psh   # just the PSH-RP phase

Each phase: converge, 100 pings/s from h1 to h2, link r1-r2 degrades for --ramp seconds,
then it dies silently (blackhole). A line per second shows how many replies h1 still gets.
"""
import argparse
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import netem_ctl
import psh_failover_test as P
import psh_topo as T
from ping_analysis import analyze, parse_ping


def say(msg):
    print(msg, flush=True)


def monitor(stop, state):
    t0, seen = time.time(), 0
    while not stop.is_set():
        time.sleep(1)
        try:
            with open(P.PING_FILE) as f:
                n = f.read().count("bytes from")
        except OSError:
            n = 0
        say(f"  [{time.time() - t0:4.0f} s] {state['phase']:<9} replies this second: {n - seen:3d}   {state['note']}")
        seen = n


def run_phase(psh, args):
    net = T.build_net(2)
    net.start()
    T.set_ips(net)
    eng = swapper = None
    state = {"phase": "starting", "note": ""}
    stop = threading.Event()
    try:
        T.write_configs("ospf", "tuned")
        T.start_frr(net, "ospf")
        if T.wait_converged(net) is None:
            sys.exit("Network never converged.")
        time.sleep(5)
        if psh:
            from engine.engine import Engine
            from engine.telemetry import make_probe_fn
            links = {f"{x}-{y}": (net[x], f"{x}-{y}", f"10.0.{i}.2") for i, (x, y) in enumerate(T.LINKS, 1)}
            swapper = P.Swapper(net)

            def at_risk(link, ts):
                swapper.on_at_risk(link, ts)
                if link in swapper.standby:
                    say(f"  >>> PSH-RP: {link} is degrading, backup path {'-'.join(swapper.standby[link] or [])} prepared")

            def hard_cutoff(link, ts):
                swapper.on_hard_cutoff(link, ts)
                if swapper.active:
                    state["note"] = "BACKUP ACTIVE via " + "-".join(swapper.active[1])
                    say(f"  >>> PSH-RP: traffic moved to {'-'.join(swapper.active[1])}, link still up")

            eng = Engine(links, make_probe_fn(links), at_risk, hard_cutoff, swapper.on_clear, tag="demo")
            eng.start()
        total = args.baseline + args.ramp + args.post
        net["h1"].cmd(f"rm -f {P.PING_FILE}; ping -D -i 0.01 -W 1 -c {int((total + 6) * 100)} 192.168.2.10 > {P.PING_FILE} 2>&1 &")
        threading.Thread(target=monitor, args=(stop, state), daemon=True).start()
        state["phase"] = "healthy"
        time.sleep(args.baseline)
        state["phase"] = "degrading"
        say("  *** link r1-r2 starts degrading (delay, jitter and loss rise)")
        netem_ctl.ramp(net, "r1", "r2", duration=args.ramp, steps=args.ramp, then_cut=False)
        state["phase"] = "FAILED"
        t_fail = netem_ctl.blackhole(net, "r1", "r2")
        say("  *** link r1-r2 DIES (silent failure)")
        time.sleep(args.post)
        stop.set()
        net["h1"].cmd("pkill -INT ping")
        time.sleep(2)
        with open(P.PING_FILE) as f:
            text = f.read()
    finally:
        stop.set()
        if eng:
            eng.stop()
        net.stop()
        T.stop_frr()
    res = analyze(parse_ping(text), t_fail)
    m = P.SUMMARY.findall(text)
    lost = int(m[-1][0]) - int(m[-1][1]) if m else -1
    swap = swapper.swap_ts() if swapper else None
    return res["conv_time"], lost, (t_fail - swap) if swap else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["plain", "psh"], default=None)
    ap.add_argument("--baseline", type=float, default=38, help="healthy seconds (the engine needs about 30 s to warm up)")
    ap.add_argument("--ramp", type=int, default=30)
    ap.add_argument("--post", type=float, default=15)
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    results = {}
    for name, psh in (("plain OSPF (tuned timers)", False), ("PSH-RP on OSPF", True)):
        if args.only and (args.only == "psh") != psh:
            continue
        os.system("mn -c >/dev/null 2>&1")
        say(f"\n=== {name}: same degradation, same failure ===")
        results[name] = run_phase(psh, args)
    say("\n=== Result ===")
    say(f"{'':28}{'outage after failure':>22}{'packets lost':>15}{'backup ready':>16}")
    for name, (outage, lost, lead) in results.items():
        ready = f"{lead:.0f} s before" if lead else "no"
        say(f"{name:28}{outage:>19.2f} s{lost:>15}{ready:>16}")


if __name__ == "__main__":
    main()
