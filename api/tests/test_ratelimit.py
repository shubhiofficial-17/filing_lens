from app.ratelimit import RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_bucket_allows_a_burst_then_refills():
    clock = Clock()
    limiter = RateLimiter(3, clock=clock)
    assert [limiter.check("a") for _ in range(3)] == [None, None, None]
    wait = limiter.check("a")
    assert wait is not None and 19 < wait <= 20  # one token per 20 seconds
    assert limiter.check("b") is None  # other clients are separate
    clock.now = 20.0
    assert limiter.check("a") is None


def test_zero_disables_the_limit():
    limiter = RateLimiter(0)
    assert all(limiter.check("a") is None for _ in range(100))


def test_idle_clients_are_evicted():
    clock = Clock()
    limiter = RateLimiter(60, clock=clock, max_clients=2)
    for key in ("a", "b"):
        limiter.check(key)
    clock.now = 120.0
    limiter.check("c")
    assert set(limiter._buckets) == {"c"}
