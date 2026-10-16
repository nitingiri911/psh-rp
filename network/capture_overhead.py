#!/usr/bin/env python3
"""
Control-traffic overhead (Member 1): how many bytes per second does each routing
protocol put on ONE link (r1-r2), compared with one PSH-RP style probe per second?

For each config the network converges, settles for 10 s, then tcpdump runs on r1's
interface towards r2 for --secs seconds with a protocol filter:
    OSPF  -> ip proto 89        RIP -> udp port 520
    probe -> icmp  (one ping per second, both directions seen on the interface)
Results are appended to logs/overhead.csv.

    sudo python3 capture_overhead.py --secs 120
"""
import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

LOGS = Path(__file__).resolve().parent.parent / "logs"
_LEN = re.compile(r"length (\d+):")


def parse_tcpdump(text):
    """(packets, bytes) from `tcpdump -e` text output. Frame length includes the Ethernet header."""
    lens = [int(m.group(1)) for line in text.splitlines()
            for m in [_LEN.search(line)] if m]
    return len(lens), sum(lens)


def capture(T, proto, timers, secs, probe=False):
    net = T.build_net(2)
    net.start()
    T.set_ips(net)
    try:
        T.write_configs(proto, timers)
        T.start_frr(net, proto)
        if T.wait_converged(net) is None:
            sys.exit("Network never converged, capture aborted.")
        time.sleep(10)
        r1 = net["r1"]
        flt = "icmp" if probe else ("ip proto 89" if proto == "ospf" else "udp port 520")
        out = f"/tmp/pshrp_cap_{proto}_{timers}_{'probe' if probe else 'ctl'}.txt"
        r1.cmd(f"rm -f {out}; timeout {secs + 2} tcpdump -i r1-r2 -nn -e -l -p {flt} > {out} 2>&1 &")
        time.sleep(1)
        if probe:
            r1.cmd(f"ping -i 1 -c {secs} -I r1-r2 10.0.1.2 > /dev/null 2>&1 &")
        time.sleep(secs + 4)
        with open(out) as f:
            text = f.read()
    finally:
        net.stop()
        T.stop_frr()
    return parse_tcpdump(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=int, default=120, help="capture length per config")
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    import psh_topo as T  # imported here so parse_tcpdump can be tested without Mininet

    LOGS.mkdir(exist_ok=True)
    path = LOGS / "overhead.csv"
    new = not path.exists()
    rows = []
    jobs = [("ospf_default", "ospf", "default", False), ("ospf_tuned", "ospf", "tuned", False),
            ("rip_default", "rip", "default", False), ("rip_tuned", "rip", "tuned", False),
            ("psh_probe_1_per_s", "ospf", "default", True)]
    for name, proto, timers, probe in jobs:
        os.system("mn -c >/dev/null 2>&1")
        pk, by = capture(T, proto, timers, args.secs, probe)
        rows.append([name, args.secs, pk, by, round(by / args.secs, 1), round(pk / args.secs, 3)])
        print(f"RESULT {name}: {pk} packets, {by} bytes, {by / args.secs:.1f} bytes/s")
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["config", "seconds", "packets", "bytes", "bytes_per_s", "packets_per_s"])
        w.writerows(rows)
    print(f"Saved to {path}")


if __name__ == "__main__":
    main()
