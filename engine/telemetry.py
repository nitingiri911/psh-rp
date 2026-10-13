import re
from engine import config as c

RTT = re.compile(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms")
LOSS = re.compile(r"([\d.]+)% packet loss")


def probe(node, intf, dst):
    p = node.popen(["ping", "-I", intf, "-c", str(c.PROBES), "-i", str(c.PROBE_GAP), "-W", "1", dst])
    out, _ = p.communicate()
    if isinstance(out, bytes):
        out = out.decode()
    m = LOSS.search(out)
    loss = float(m.group(1)) if m else 100.0
    r = RTT.search(out)
    if r is None:
        return {"latency": c.LAT_MAX, "jitter": 0.0, "loss": loss}
    return {"latency": float(r.group(2)), "jitter": float(r.group(4)), "loss": loss}


def make_probe_fn(links):
    return lambda link: probe(*links[link])
