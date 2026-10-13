"""
Link degradation and failure helpers (tc netem), used by experiments.

All functions take the Mininet `net` object and the two router names of a link.
They act on BOTH directions of the link. Timestamps are time.time() (epoch seconds),
so they can be compared directly with Nitin's at-risk log and Arsh's swap log.
"""
import time


def _apply(net, a, b, opts):
    for x, y in ((a, b), (b, a)):
        net[x].cmd(f"tc qdisc replace dev {x}-{y} root netem {opts}")


def degrade(net, a, b, delay_ms=2.0, jitter_ms=0.0, loss_pct=0.0):
    _apply(net, a, b, f"delay {delay_ms:.1f}ms {jitter_ms:.1f}ms loss {loss_pct:.2f}%")


def restore(net, a, b, delay_ms=2.0):
    degrade(net, a, b, delay_ms, 0.0, 0.0)


def cut(net, a, b):
    """Hard failure. Returns the cut timestamp."""
    t = time.time()
    net.configLinkStatus(a, b, "down")
    return t


def heal(net, a, b):
    net.configLinkStatus(a, b, "up")


def make_noisy(net, a, b, delay_ms=20.0, jitter_ms=15.0, loss_pct=1.0):
    """Permanently jittery but healthy link (false-alarm test, scenario S4)."""
    degrade(net, a, b, delay_ms, jitter_ms, loss_pct)


def ramp(net, a, b, duration=30, steps=30, start_delay=2.0, max_delay=200.0,
         max_jitter=40.0, max_loss=20.0, then_cut=True, log=print):
    """
    Gradual degradation (scenarios S1/S2): delay, jitter and loss grow linearly
    over `duration` seconds, then the link is cut (if then_cut).
    Slow ramp = large duration, fast ramp = small duration.
    Returns {"ramp_start": t0, "cut": t_cut or None}.
    """
    t0 = time.time()
    log(f"[netem] ramp start {a}-{b} at {t0:.3f}")
    for i in range(1, steps + 1):
        f = i / steps
        degrade(net, a, b,
                start_delay + f * (max_delay - start_delay),
                f * max_jitter,
                f * max_loss)
        time.sleep(duration / steps)
    t_cut = None
    if then_cut:
        t_cut = cut(net, a, b)
        log(f"[netem] link {a}-{b} cut at {t_cut:.3f}")
    return {"ramp_start": t0, "cut": t_cut}
