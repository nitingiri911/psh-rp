#!/usr/bin/env python3
"""
Live demo (Member 1): the same degrading link, first with plain OSPF, then with PSH-RP.

    sudo python3 network/demo.py                 # both phases, about 4 minutes
    sudo python3 network/demo.py --only psh      # just the PSH-RP phase
    sudo python3 network/demo.py --manager builtin   # use the swap logic in psh_failover_test.py
    sudo python3 network/demo.py --timers default --post 45   # recommended: plain OSPF then shows its full outage
    sudo python3 network/demo.py --timers default --post 45   # recommended: plain OSPF then shows its full outage

Each phase: converge, 100 pings/s from h1 to h2, link r1-r2 degrades for --ramp seconds,
then it dies silently (blackhole). By default the PSH-RP phase uses Arsh's forwarding table manager.
"lost" is counted from gaps in the ping sequence numbers, so a slow ping sender is not counted as loss.
During a total outage no replies arrive, so the line says NO REPLIES, and the lost count appears when replies resume.
"""
import argparse
import os
import re
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

SEQ = re.compile(r"bytes from [^\n]*?icmp_seq=(\d+)")


def say(msg):
    print(msg, flush=True)


def monitor(stop, state):
    """One line per second. Loss is counted from missing icmp_seq numbers, so a slow ping sender is not loss."""
    t0 = time.time()
    seen = hi_prev = lost_prev = 0
    while not stop.is_set():
        time.sleep(1)
        try:
            with open(P.PING_FILE) as f:
                text = f.read()
        except OSError:
            continue
        seqs = SEQ.findall(text)
        n = text.count("bytes from")
        hi = max(map(int, seqs)) if seqs else 0
        got, sent = n - seen, hi - hi_prev
        gap = max((hi - n) - lost_prev, 0)
        pct = 100.0 * gap / sent if sent > 0 else 0.0
        note = state["note"] or ("NO REPLIES" if got == 0 else "")
        say(f"  [{time.time() - t0:4.0f} s] {state['phase']:<9} replies: {got:3d}  lost: {gap:3d} ({pct:3.0f}%)  {note}")
        seen, hi_prev, lost_prev = n, hi, hi - n


def routers(path):
    return "-".join(n for n in (path or []) if n.startswith("r"))


def run_phase(psh, args):
    net = T.build_net(2)
    net.start()
    T.set_ips(net)
    eng = swapper = None
    state = {"phase": "starting", "note": ""}
    stop = threading.Event()
    try:
        T.write_configs("ospf", args.timers)
        T.start_frr(net, "ospf")
        if T.wait_converged(net) is None:
            sys.exit("Network never converged.")
        time.sleep(5)
        if psh:
            from engine.engine import Engine
            from engine.telemetry import make_probe_fn
            links = {f"{x}-{y}": (net[x], f"{x}-{y}", f"10.0.{i}.2") for i, (x, y) in enumerate(T.LINKS, 1)}
            fib = args.manager == "fib"
            swapper = P.FibAdapter(net) if fib else P.Swapper(net)

            def standby(link):
                if fib:
                    return next((p for (l, _f), p in swapper.mgr.standby.items() if l == link), None)
                return swapper.standby.get(link)

            def active():
                if not swapper.swap_ts():
                    return None
                return swapper.mgr.active[("h1", "h2")] if fib else swapper.active[1]

            def at_risk(link, ts):
                swapper.on_at_risk(link, ts)
                if standby(link):
                    say(f"  >>> PSH-RP: {link} is degrading, backup path {routers(standby(link))} prepared")

            def hard_cutoff(link, ts):
                swapper.on_hard_cutoff(link, ts)
                if active():
                    state["note"] = "BACKUP ACTIVE via " + routers(active())
                    say(f"  >>> PSH-RP: traffic moved to {routers(active())}, link still up")

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
    ap.add_argument("--manager", choices=["fib", "builtin"], default="fib",
                    help="fib = Arsh's forwarding table manager (default), builtin = logic in psh_failover_test.py")
    ap.add_argument("--timers", choices=["tuned", "default"], default="tuned",
                    help="OSPF timers. Use default (with --post 45) so plain OSPF shows its full outage")
    ap.add_argument("--baseline", type=float, default=38, help="healthy seconds (the engine needs about 30 s to warm up)")
    ap.add_argument("--ramp", type=int, default=30)
    ap.add_argument("--post", type=float, default=15)
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    results = {}
    for name, psh in ((f"plain OSPF ({args.timers} timers)", False), (f"PSH-RP on OSPF ({args.timers})", True)):
        if args.only and (args.only == "psh") != psh:
            continue
        os.system("mn -c >/dev/null 2>&1")
        say(f"\n=== {name}: same degradation, same failure ===")
        results[name] = run_phase(psh, args)
    say("\n=== Result (one short run, not the 10-run statistics) ===")
    say(f"{'':34}{'outage after failure':>22}{'packets lost':>15}{'backup ready':>16}")
    for name, (outage, lost, lead) in results.items():
        ready = f"{lead:.0f} s before" if lead else "no"
        say(f"{name:34}{outage:>19.2f} s{lost:>15}{ready:>16}")


if __name__ == "__main__":
    main()
