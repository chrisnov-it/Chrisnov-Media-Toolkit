"""Unit tests for app/progress.py — ETA formatting and estimation."""

from app.progress import EtaEstimator, format_eta


class TestFormatEta:
    def test_none_and_invalid(self):
        assert format_eta(None) == "--:--"
        assert format_eta(float("nan")) == "--:--"
        assert format_eta(-5.0) == "--:--"

    def test_minutes_seconds(self):
        assert format_eta(0) == "00:00"
        assert format_eta(32.4) == "00:32"
        assert format_eta(90) == "01:30"

    def test_hours(self):
        assert format_eta(3725) == "1:02:05"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _estimator(floor=10, ceiling=90):
    clock = FakeClock()
    est = EtaEstimator(clock=clock)
    est.reset(floor, ceiling)
    return est, clock


class TestEtaEstimator:
    def test_no_estimate_before_reset(self):
        est = EtaEstimator(clock=FakeClock())
        assert est.update(50) is None

    def test_no_estimate_at_floor(self):
        est, _ = _estimator()
        assert est.update(10) is None

    def test_no_estimate_too_early(self):
        est, clock = _estimator()
        clock.now += 0.5  # below MIN_ELAPSED
        assert est.update(50) is None

    def test_linear_estimate(self):
        est, clock = _estimator()
        clock.now += 10.0  # 10s elapsed
        # frac = (50-10)/80 = 0.5 -> remaining = 10s -> "00:10"
        assert est.update(50) == "00:10"

    def test_no_estimate_near_completion(self):
        est, clock = _estimator()
        clock.now += 60.0
        assert est.update(90) is None  # frac = 1.0
        assert est.update(100) is None

    def test_ebu_range(self):
        est, clock = _estimator(floor=5, ceiling=90)
        clock.now += 20.0
        # frac = (40-5)/85 ≈ 0.41 -> remaining ≈ 28.6s -> "00:29"
        assert est.update(40) == "00:29"

    def test_retry_drop_rebases(self):
        est, clock = _estimator()
        clock.now += 10.0
        assert est.update(80) == "00:01"
        clock.now += 1.0
        # Progress fell back (video AAC/Opus retry) -> None, clock rebased
        assert est.update(12) is None
        clock.now += 10.0
        assert est.update(50) == "00:10"
