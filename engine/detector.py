from collections import deque
from statistics import mean, pstdev
from engine import config as c


class LinkDetector:
    def __init__(self, adaptive=True, hard=True):
        self.adaptive = adaptive
        self.hard = hard
        self.hist = deque(maxlen=c.HIST)
        self.seen = 0
        self.bad = 0
        self.good = 0
        self.at_risk = False
        self.cut = False
        self.threshold = c.FIXED_THRESHOLD

    def _threshold(self):
        if not self.adaptive or self.seen < c.WARMUP or len(self.hist) < c.MIN_HIST:
            return c.FIXED_THRESHOLD
        sd = max(pstdev(self.hist), c.MIN_STD)
        return mean(self.hist) - c.SIGMA_K * sd

    def update(self, health):
        self.threshold = self._threshold()
        self.seen += 1
        below = health < self.threshold
        if below:
            self.bad += 1
            self.good = 0
        else:
            self.good += 1
            self.bad = 0
        events = []
        if not self.at_risk and self.bad >= c.N_CONSEC:
            self.at_risk = True
            events.append("at_risk")
        elif self.at_risk and self.good >= c.CLEAR_M:
            self.at_risk = False
            self.cut = False
            events.append("clear")
        if self.hard and health < c.HARD_CUTOFF and not self.cut:
            if not self.at_risk:
                self.at_risk = True
                events.append("at_risk")
            self.cut = True
            events.append("hard_cutoff")
        if c.FREEZE_MODE == "below":
            if not below:
                self.hist.append(health)
        elif c.FREEZE_MODE == "alert":
            if not self.at_risk:
                self.hist.append(health)
        else:
            self.hist.append(health)
        return self.threshold, self.at_risk, events
