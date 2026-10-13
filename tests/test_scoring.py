from engine.scoring import LinkScorer, slope


def test_slope_linear():
    assert abs(slope([0, 1, 2, 3, 4]) - 1.0) < 1e-9


def test_slope_flat_and_short():
    assert slope([5, 5, 5, 5]) == 0.0
    assert slope([1, 2]) == 0.0


def test_healthy_link_scores_high():
    s = LinkScorer()
    h = 0
    for _ in range(10):
        h = s.update(10, 1, 0)
    assert h > 95


def test_total_outage_scores_zero():
    s = LinkScorer(alpha=0.0)
    assert s.update(500, 500, 100) == 0.0


def test_trend_lowers_health_on_rising_metrics():
    with_trend = LinkScorer(alpha=2.0)
    without = LinkScorer(alpha=0.0)
    a = b = 0
    for i in range(30):
        lat = 10 + i * 5
        a = with_trend.update(lat, 1, 0)
        b = without.update(lat, 1, 0)
    assert a < b
