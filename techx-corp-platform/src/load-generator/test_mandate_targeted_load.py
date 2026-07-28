import unittest

from mandate_targeted_load import TargetedLoadConfig, run_targeted_load


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, statuses=None):
        self.statuses = iter(statuses or [])
        self.calls = []

    def _response(self):
        return FakeResponse(next(self.statuses, 200))

    def get(self, url, headers, timeout):
        self.calls.append(("GET", url, None, headers, timeout))
        return self._response()

    def post(self, url, json, headers, timeout):
        self.calls.append(("POST", url, json, headers, timeout))
        return self._response()


def config(**overrides):
    values = {
        "scenario": "product-reviews",
        "owner": "hoa",
        "run_id": "m15-test",
        "max_requests": 3,
        "workers": 1,
        "pace_seconds": 0.05,
        "execute": True,
    }
    values.update(overrides)
    return TargetedLoadConfig(**values)


class TargetedLoadConfigTests(unittest.TestCase):
    def test_requires_owner_and_bounded_limits(self):
        with self.assertRaisesRegex(ValueError, "owner"):
            config(owner="").validate()
        with self.assertRaisesRegex(ValueError, "max-requests"):
            config(max_requests=5_001).validate()
        with self.assertRaisesRegex(ValueError, "workers"):
            config(workers=51).validate()

    def test_rejects_public_or_accidental_host(self):
        with self.assertRaisesRegex(ValueError, "in-cluster proxy"):
            config(base_url="https://example.com").validate()

    def test_plan_mode_sends_no_traffic(self):
        session = FakeSession()
        result = run_targeted_load(
            config(execute=False),
            session_factory=lambda: session,
        )
        self.assertEqual(result["status"], "planned")
        self.assertEqual(session.calls, [])


class TargetedLoadExecutionTests(unittest.TestCase):
    def test_product_review_uses_one_cache_friendly_product_route(self):
        session = FakeSession()
        result = run_targeted_load(
            config(max_requests=3),
            session_factory=lambda: session,
            sleep=lambda _: None,
        )
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["failures"], 0)
        self.assertEqual(
            [call[1] for call in session.calls],
            [
                "http://frontend-proxy:8080/api/product-reviews/0PUK6V6EV0",
                "http://frontend-proxy:8080/api/product-reviews/0PUK6V6EV0",
                "http://frontend-proxy:8080/api/product-reviews/0PUK6V6EV0",
            ],
        )

    def test_checkout_preloads_cart_before_each_checkout(self):
        session = FakeSession()
        person = {"email": "defense@example.com", "address": {"city": "Da Nang"}}
        result = run_targeted_load(
            config(scenario="checkout", max_requests=2),
            people=[person],
            session_factory=lambda: session,
            sleep=lambda _: None,
        )
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(
            [call[1] for call in session.calls],
            [
                "http://frontend-proxy:8080/api/cart",
                "http://frontend-proxy:8080/api/checkout",
                "http://frontend-proxy:8080/api/cart",
                "http://frontend-proxy:8080/api/checkout",
            ],
        )
        self.assertNotIn("userId", person)
        self.assertTrue(session.calls[1][2]["userId"].startswith("m15-test-"))
        self.assertEqual(session.calls[1][3]["X-TF4-Load-Owner"], "hoa")
        self.assertEqual(result["maximum_http_requests"], 4)

    def test_checkout_rejects_empty_person_payload_set(self):
        with self.assertRaisesRegex(ValueError, "person payload"):
            run_targeted_load(
                config(scenario="checkout"),
                people=[],
                session_factory=FakeSession,
                sleep=lambda _: None,
            )

    def test_rolling_failure_guard_stops_the_run(self):
        session = FakeSession(statuses=[503] * 100)
        result = run_targeted_load(
            config(
                max_requests=200,
                failure_window=20,
                failure_stop_ratio=0.10,
            ),
            session_factory=lambda: session,
            sleep=lambda _: None,
        )
        self.assertEqual(result["status"], "stopped_by_failure_guard")
        self.assertEqual(result["attempts"], 20)
        self.assertEqual(result["failures"], 20)


if __name__ == "__main__":
    unittest.main()
