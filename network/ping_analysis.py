"""Turn `ping -D` output into outage numbers. Pure Python, no Mininet needed."""
import re

_RE = re.compile(r"^\[(\d+\.\d+)\]\s+\d+ bytes from .*icmp_seq=(\d+)")
NAN = float("nan")


def parse_ping(text):
    """[(timestamp, seq)] for every received reply in `ping -D` output."""
    out = []
    for line in text.splitlines():
        m = _RE.match(line)
        if m:
            out.append((float(m.group(1)), int(m.group(2))))
    return sorted(out, key=lambda r: r[1])


def analyze(replies, t_cut, min_gap=3):
    """
    Find the run of missing replies that starts at the failure.
    Returns {"recovered": bool, "conv_time": s after t_cut until traffic flows again,
             "lost": packets lost}. With 100 packets/s, one lost packet = 10 ms.
    """
    if not replies:
        return {"recovered": False, "conv_time": NAN, "lost": NAN}
    best = None
    for (t0, s0), (t1, s1) in zip(replies, replies[1:]):
        missing = s1 - s0 - 1
        if missing >= min_gap and t0 <= t_cut + 1.0 and t1 > t_cut:
            if best is None or missing > best[0]:
                best = (missing, t1)
    if best:
        return {"recovered": True, "conv_time": max(0.0, best[1] - t_cut), "lost": best[0]}
    if replies[-1][0] > t_cut + 1.0:
        return {"recovered": True, "conv_time": 0.0, "lost": 0}
    return {"recovered": False, "conv_time": NAN, "lost": NAN}
