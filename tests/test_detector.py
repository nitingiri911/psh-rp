import random
from engine import config as c
from engine.detector import LinkDetector


def flags(det, seq):
    out = []
    for i, h in enumerate(seq):
        _, _, evs = det.update(h)
        for e in evs:
            out.append((i, e))
    return out


def healthy(n, mean=95, sd=1, seed=1):
    random.seed(seed)
    return [mean + random.gauss(0, sd) for _ in range(n)]


def test_warmup_uses_fixed_threshold():
    det = LinkDetector(True)
    for h in healthy(c.WARMUP):
        th, _, _ = det.update(h)
        assert th == c.FIXED_THRESHOLD
    th, _, _ = det.update(95)
    assert th != c.FIXED_THRESHOLD


def test_gradual_ramp_flagged_after_baseline():
    seq = healthy(60) + [95 - i * 1.5 for i in range(40)]
    ev = flags(LinkDetector(True), seq)
    first = [i for i, e in ev if e == "at_risk"]
    assert first and 60 <= first[0] < 70


def test_adaptive_catches_ramp_before_fixed():
    seq = healthy(60) + [95 - i * 0.8 for i in range(60)]
    a = [i for i, e in flags(LinkDetector(True, False), seq) if e == "at_risk"]
    f = [i for i, e in flags(LinkDetector(False, False), seq) if e == "at_risk"]
    assert a and f and a[0] < f[0]


def test_noisy_link_adaptive_far_quieter_than_fixed():
    a = f = 0
    for seed in range(50):
        random.seed(seed)
        seq = [90 + random.gauss(0, 4) for _ in range(600)]
        a += sum(1 for _, e in flags(LinkDetector(True, False), seq) if e == "at_risk")
        f += sum(1 for _, e in flags(LinkDetector(False, False), seq) if e == "at_risk")
    assert f > 0 and a * 3 < f


def test_hysteresis_before_clear():
    det = LinkDetector(True, False)
    for h in healthy(40):
        det.update(h)
    for _ in range(c.N_CONSEC):
        det.update(60)
    assert det.at_risk
    for _ in range(c.CLEAR_M - 1):
        det.update(96)
    assert det.at_risk
    _, risk, evs = det.update(96)
    assert not risk and evs == ["clear"]


def test_hard_cutoff_fires_once_and_implies_at_risk():
    det = LinkDetector(True, True)
    for h in healthy(40):
        det.update(h)
    _, _, e1 = det.update(c.HARD_CUTOFF - 10)
    _, _, e2 = det.update(c.HARD_CUTOFF - 10)
    assert e1 == ["at_risk", "hard_cutoff"]
    assert e2 == []


def test_hard_cutoff_disabled():
    det = LinkDetector(True, False)
    for h in healthy(40):
        det.update(h)
    evs = []
    for _ in range(5):
        evs += det.update(5)[2]
    assert "hard_cutoff" not in evs
