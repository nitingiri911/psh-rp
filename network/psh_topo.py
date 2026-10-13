#!/usr/bin/env python3
"""
PSH-RP test topology (Member 1: Network and Baselines)

6 routers (r1..r6) + 2 hosts (h1, h2), each router runs FRRouting
(zebra + ospfd or ripd) inside its own Mininet node.

    h1 -- r1 ---- r2 ---- r6 -- h2          primary   (shortest)
           \\      |  \\    /
            \\     |   r5 /                  r2-r5 = noisy link (false-alarm test)
             r3 -- r4 ----                  alternate (r1-r3-r4-r6)

Usage (needs root):
    sudo python3 psh_topo.py --proto ospf                # OSPF, default timers, CLI
    sudo python3 psh_topo.py --proto ospf --timers tuned # hello 1s / dead 3s
    sudo python3 psh_topo.py --proto rip
    sudo python3 psh_topo.py --proto ospf --check        # Week 1 gate: converge, print, exit

Naming contract (shared with Nitin and Arsh):
    routers      r1..r6, hosts h1, h2
    interfaces   "<self>-<peer>"  e.g. r1-r2 is r1's interface towards r2
    link subnets 10.0.<i>.0/30 (i = index in LINKS, first node .1, second .2)
    host LANs    192.168.1.0/24 (h1 .10, r1 .1), 192.168.2.0/24 (h2 .10, r6 .1)
"""
import argparse
import os
import shutil
import sys
import time

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Node

import netem_ctl

FRR_DIR = "/usr/lib/frr"
RUN_DIR = "/tmp/pshrp"

ROUTERS = ["r1", "r2", "r3", "r4", "r5", "r6"]
HOSTS = {"h1": ("r1", "192.168.1"), "h2": ("r6", "192.168.2")}
LINKS = [
    ("r1", "r2"),  # 1  primary
    ("r2", "r6"),  # 2  primary
    ("r1", "r3"),  # 3  alternate
    ("r3", "r4"),  # 4  alternate
    ("r4", "r6"),  # 5  alternate
    ("r2", "r5"),  # 6  noisy cross link
    ("r5", "r4"),  # 7  cross link
]
NOISY_LINK = ("r2", "r5")


class LinuxRouter(Node):
    """A Mininet node with IP forwarding switched on."""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


def router_ifaces(r):
    """[(ifname, prefix, is_host_lan)] for router r."""
    out = []
    for i, (a, b) in enumerate(LINKS, 1):
        if r == a:
            out.append((f"{a}-{b}", f"10.0.{i}.0/30", False))
        elif r == b:
            out.append((f"{b}-{a}", f"10.0.{i}.0/30", False))
    for h, (rr, net) in HOSTS.items():
        if r == rr:
            out.append((f"{r}-{h}", f"{net}.0/24", True))
    return out


def build_net(base_delay_ms):
    net = Mininet(controller=None, link=TCLink, autoSetMacs=True)
    for r in ROUTERS:
        net.addHost(r, cls=LinuxRouter)
    for h in HOSTS:
        net.addHost(h)

    for i, (a, b) in enumerate(LINKS, 1):
        net.addLink(
            a, b,
            intfName1=f"{a}-{b}", intfName2=f"{b}-{a}",
            params1={"ip": f"10.0.{i}.1/30"},
            params2={"ip": f"10.0.{i}.2/30"},
            delay=f"{base_delay_ms}ms",
        )
    for h, (r, subnet) in HOSTS.items():
        net.addLink(
            r, h,
            intfName1=f"{r}-{h}", intfName2=f"{h}-eth0",
            params1={"ip": f"{subnet}.1/24"},
            params2={"ip": f"{subnet}.10/24"},
        )
    return net


def set_ips(net):
    """Mininet overwrites each node's first interface IP with 10.0.0.x, so set them all explicitly."""
    def put(node, intf, cidr):
        node.cmd(f"ip -4 addr flush dev {intf}")
        node.cmd(f"ip addr add {cidr} dev {intf}")
        node.cmd(f"ip link set {intf} up")

    for i, (a, b) in enumerate(LINKS, 1):
        put(net[a], f"{a}-{b}", f"10.0.{i}.1/30")
        put(net[b], f"{b}-{a}", f"10.0.{i}.2/30")
    for h, (r, subnet) in HOSTS.items():
        put(net[r], f"{r}-{h}", f"{subnet}.1/24")
        put(net[h], f"{h}-eth0", f"{subnet}.10/24")
        net[h].cmd(f"ip route add default via {subnet}.1")


def write_configs(proto, timers):
    shutil.rmtree(RUN_DIR, ignore_errors=True)
    for idx, r in enumerate(ROUTERS, 1):
        d = f"{RUN_DIR}/{r}"
        os.makedirs(d)
        with open(f"{d}/zebra.conf", "w") as f:
            f.write(f"hostname {r}-zebra\nlog file {d}/zebra.log\n")

        ifaces = router_ifaces(r)
        if proto == "ospf":
            lines = [f"hostname {r}-ospfd", f"log file {d}/ospfd.log", "!"]
            for ifname, _, host_lan in ifaces:
                lines.append(f"interface {ifname}")
                if not host_lan:
                    lines.append(" ip ospf network point-to-point")
                    if timers == "tuned":
                        lines.append(" ip ospf hello-interval 1")
                        lines.append(" ip ospf dead-interval 3")
                lines.append("!")
            lines.append("router ospf")
            lines.append(f" ospf router-id 1.1.1.{idx}")
            for ifname, prefix, host_lan in ifaces:
                lines.append(f" network {prefix} area 0")
                if host_lan:
                    lines.append(f" passive-interface {ifname}")
            lines.append("!")
            conf = "ospfd.conf"
        else:
            lines = [f"hostname {r}-ripd", f"log file {d}/ripd.log", "!", "router rip", " version 2",
                     " network 10.0.0.0/8", " network 192.168.0.0/16"]
            for ifname, _, host_lan in ifaces:
                if host_lan:
                    lines.append(f" passive-interface {ifname}")
            if timers == "tuned":
                lines.append(" timers basic 5 15 10")  # update, timeout, garbage
            lines.append("!")
            conf = "ripd.conf"
        with open(f"{d}/{conf}", "w") as f:
            f.write("\n".join(lines) + "\n")


def _run(net, r, cmd):
    """Run a command on router r and show any error text it prints."""
    out = net[r].cmd(cmd + " 2>&1")
    if out.strip():
        info(f"[{r}] {out.strip()}\n")


def start_frr(net, proto):
    daemon = f"{proto}d"
    for r in ROUTERS:
        d = f"{RUN_DIR}/{r}"
        common = f"-d -u root -g root -A 127.0.0.1 -z {d}/zserv.api --vty_socket {d}"
        _run(net, r, f"{FRR_DIR}/zebra {common} -f {d}/zebra.conf -i {d}/zebra.pid")
    time.sleep(1)
    for r in ROUTERS:
        d = f"{RUN_DIR}/{r}"
        common = f"-d -u root -g root -A 127.0.0.1 -z {d}/zserv.api --vty_socket {d}"
        _run(net, r, f"{FRR_DIR}/{daemon} {common} -f {d}/{daemon}.conf -i {d}/{daemon}.pid")


def stop_frr():
    os.system(f"pkill -f '{FRR_DIR}/' >/dev/null 2>&1")


def vtysh(net, router, command):
    """Run one FRR command on a router, e.g. vtysh(net, 'r1', 'show ip ospf neighbor')."""
    return net[router].cmd(f"vtysh --vty_socket {RUN_DIR}/{router} -c '{command}'")


def wait_converged(net, timeout=90):
    """Seconds until h1 can ping h2, or None on timeout."""
    h1 = net["h1"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        if " 1 received" in h1.cmd("ping -c1 -W1 192.168.2.10"):
            return time.time() - t0
        time.sleep(1)
    return None


def main():
    ap = argparse.ArgumentParser(description="PSH-RP Mininet + FRR topology")
    ap.add_argument("--proto", choices=["ospf", "rip"], default="ospf")
    ap.add_argument("--timers", choices=["default", "tuned"], default="default")
    ap.add_argument("--delay", type=float, default=2, help="base one-way link delay in ms")
    ap.add_argument("--noisy", action="store_true", help="make r2-r5 a noisy link")
    ap.add_argument("--check", action="store_true", help="converge, print state, exit")
    args = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    for d in ("zebra", "ospfd", "ripd"):
        if not os.path.exists(f"{FRR_DIR}/{d}"):
            sys.exit(f"{FRR_DIR}/{d} not found. Run setup.sh first.")

    setLogLevel("info")
    net = build_net(args.delay)
    net.start()
    set_ips(net)
    try:
        write_configs(args.proto, args.timers)
        start_frr(net, args.proto)
        if args.noisy:
            netem_ctl.make_noisy(net, *NOISY_LINK)

        net.netem = netem_ctl  # reachable from the CLI as net.netem
        info(f"*** Waiting for {args.proto.upper()} to converge...\n")
        t = wait_converged(net)
        if t is None:
            info("*** FAILED: h1 cannot reach h2 after 90 s. Check /tmp/pshrp/<router>/*.log\n")
            if not args.check:
                CLI(net)
            sys.exit(1)
        info(f"*** h1 -> h2 reachable after {t:.1f} s\n")

        if args.check:
            info("*** r1 routing table:\n" + net["r1"].cmd("ip route") + "\n")
            info("*** r1 path to h2: " + net["r1"].cmd("ip route get 192.168.2.10"))
            if args.proto == "ospf":
                info("*** r1 OSPF neighbours:\n" + vtysh(net, "r1", "show ip ospf neighbor") + "\n")
        else:
            info("*** Useful: r1 vtysh --vty_socket /tmp/pshrp/r1 -c 'show ip route'\n")
            info("*** Useful: py net.netem.cut(net,'r2','r6')   |   h1 ping h2\n")
            CLI(net)
    finally:
        net.stop()
        stop_frr()


if __name__ == "__main__":
    main()
