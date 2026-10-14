"""Link table for Nitin's engine (see docs/interfaces.md)."""
from psh_topo import LINKS


def link_table(net):
    """
    {"r1-r2": (node_r1, "r1-r2", "10.0.1.2"), ...}
    The probe leaves node a through its interface "a-b" and targets b's IP on that link.
    """
    return {f"{a}-{b}": (net[a], f"{a}-{b}", f"10.0.{i}.2")
            for i, (a, b) in enumerate(LINKS, 1)}
