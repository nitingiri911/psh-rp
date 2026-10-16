import argparse
import csv
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "network"))

import netem_ctl
import psh_topo as T
from mininet.log import setLogLevel
from engine import config as c
from engine.engine import Engine
from engine.telemetry import make_probe_fn
from tools.summary import summarize

try:
    from routing.callbacks import on_at_risk, on_hard_cutoff, on_clear
    CALLBACKS = "routing.callbacks"
except ImportError:
    CALLBACKS = "print stubs"

    def on_at_risk(link, ts):
        print("AT_RISK", link, round(ts, 3))

    def on_hard_cutoff(link, ts):
        print("HARD_CUTOFF", link, round(ts, 3))

    def on_clear(link, ts):
        print("CLEAR", link, round(ts, 3))

SCENARIOS = {"s1": 60, "s2": 15, "s3": 0, "s4": 0}


def build_links(net):
    return {f"{a}-{b}": (net[a], f"{a}-{b}", f"10.0.{i}.2") for i, (a, b) in enumerate(T.LINKS, 1)}


def fail(net, a, b, kind):
    if kind == "blackhole":
        return netem_ctl.blackhole(net, a, b)
    return netem_ctl.cut(net, a, b)


def write_failures(tag, link, marks):
    with open(f"logs/{tag}_failures.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "link", "event"])
        w.writerow([f"{marks['ramp_start']:.3f}", link, "ramp_start"])
        if marks["cut"] is not None:
            w.writerow([f"{marks['cut']:.3f}", link, "cut"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=list(SCENARIOS), default="s1")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--link", default="r1-r2")
    ap.add_argument("--baseline", type=float, default=45)
    ap.add_argument("--after", type=float, default=10)
    ap.add_argument("--hold", type=float, default=120)
    ap.add_argument("--proto", choices=["ospf", "rip"], default="ospf")
    ap.add_argument("--timers", choices=["default", "tuned"], default="tuned")
    ap.add_argument("--noisy", action="store_true")
    ap.add_argument("--failure", choices=["down", "blackhole"], default="down")
    ap.add_argument("--phase-jitter", type=float, default=2.0)
    ap.add_argument("--interval", type=float, default=None)
    ap.add_argument("--noise-delay", type=float, default=20.0)
    ap.add_argument("--noise-jitter", type=float, default=15.0)
    ap.add_argument("--noise-loss", type=float, default=1.0)
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    if args.interval:
        c.PROBE_INTERVAL = args.interval
    tag = args.tag or args.scenario
    setLogLevel("warning")
    os.makedirs("logs", exist_ok=True)
    net = T.build_net(2)
    net.start()
    T.set_ips(net)
    eng = None
    try:
        T.write_configs(args.proto, args.timers)
        T.start_frr(net, args.proto)
        if args.noisy or args.scenario == "s4":
            netem_ctl.make_noisy(
                net, *T.NOISY_LINK,
                delay_ms=args.noise_delay, jitter_ms=args.noise_jitter, loss_pct=args.noise_loss,
            )
        t = T.wait_converged(net)
        if t is None:
            sys.exit("routing did not converge, see /tmp/pshrp/<router>/*.log")
        links = build_links(net)
        if args.scenario != "s4" and args.link not in links:
            sys.exit(f"unknown link {args.link}, choose from {list(links)}")
        print("callbacks:", CALLBACKS)
        eng = Engine(links, make_probe_fn(links), on_at_risk, on_hard_cutoff, on_clear, tag=tag)
        eng.start()
        time.sleep(args.baseline + random.uniform(0, args.phase_jitter))
        if args.scenario == "s4":
            time.sleep(args.hold)
        elif args.scenario == "s3":
            a, b = args.link.split("-")
            t_cut = fail(net, a, b, args.failure)
            write_failures(tag, args.link, {"ramp_start": t_cut, "cut": t_cut})
            time.sleep(args.after)
        else:
            a, b = args.link.split("-")
            n = SCENARIOS[args.scenario]
            marks = netem_ctl.ramp(net, a, b, duration=n, steps=n, then_cut=args.failure == "down")
            if args.failure == "blackhole":
                marks["cut"] = netem_ctl.blackhole(net, a, b)
            write_failures(tag, args.link, marks)
            time.sleep(args.after)
    finally:
        if eng:
            eng.stop()
        net.stop()
        T.stop_frr()
    summarize(tag)
    open(f"logs/{tag}_done", "w").close()
    print("logs written to logs/" + tag + "_*.csv")


if __name__ == "__main__":
    main()
