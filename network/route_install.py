"""
Install and remove static backup routes on Mininet routers (the real route swap).

A backup path is a list of routers, e.g. ["r1", "r3", "r4", "r6"]. install_path puts a
route for `prefix` on every router along it, with metric 1 so it beats the OSPF/RIP route
(metric 20). Commands run through nsenter, so they are safe to call from engine threads.
"""
import subprocess

from psh_topo import LINKS


def hop(a, b):
    """(interface on a, IP address of b on that link) for the link between routers a and b."""
    for i, (x, y) in enumerate(LINKS, 1):
        if (x, y) == (a, b):
            return f"{a}-{b}", f"10.0.{i}.2"
        if (x, y) == (b, a):
            return f"{a}-{b}", f"10.0.{i}.1"
    raise ValueError(f"no link between {a} and {b}")


def _ip(net, router, args):
    return subprocess.run(["nsenter", "-t", str(net[router].pid), "-n", "ip"] + args,
                          capture_output=True, text=True)


def install_path(net, path, prefix, metric=1):
    for a, b in zip(path, path[1:]):
        intf, nexthop = hop(a, b)
        _ip(net, a, ["route", "replace", prefix, "via", nexthop, "dev", intf, "metric", str(metric)])


def remove_path(net, path, prefix, metric=1):
    for a, b in zip(path, path[1:]):
        intf, nexthop = hop(a, b)
        _ip(net, a, ["route", "del", prefix, "via", nexthop, "dev", intf, "metric", str(metric)])
