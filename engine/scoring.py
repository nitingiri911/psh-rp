from collections import deque
from engine import config as c


def clamp(x):
    return max(0.0, min(100.0, x))


def normalise(latency, jitter, loss):
    return (
        clamp(latency / c.LAT_MAX * 100),
        clamp(jitter / c.JIT_MAX * 100),
        clamp(loss / c.LOSS_MAX * 100),
    )


def slope(ys):
    n = len(ys)
    if n < 3:
        return 0.0
    xm = (n - 1) / 2
    ym = sum(ys) / n
    num = sum((i - xm) * (y - ym) for i, y in enumerate(ys))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den


class LinkScorer:
    def __init__(self, alpha=c.ALPHA):
        self.alpha = alpha
        self.win = deque(maxlen=c.WINDOW)

    def update(self, latency, jitter, loss):
        ln, jn, pn = normalise(latency, jitter, loss)
        self.win.append((ln, jn, pn))
        w1, w2, w3 = c.WEIGHTS
        level = w1 * ln + w2 * jn + w3 * pn
        trend = 0.0
        if self.alpha:
            trend = self.alpha * sum(slope(col) for col in zip(*self.win))
        return clamp(100 - (level + trend))
