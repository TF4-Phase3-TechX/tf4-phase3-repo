import ast
from pathlib import Path
import unittest

from paid_ai_control import PaidAIConfig, PaidAIRequestBudget


LOCUSTFILE = Path(__file__).with_name("locustfile.py")
PAID_AI_ROUTE = "/api/product-ask-ai-assistant/"


def _class_node(tree, class_name):
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )


def _string_literals(node):
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


class PaidAIConfigTests(unittest.TestCase):
    def test_paid_ai_is_disabled_by_default(self):
        self.assertEqual(PaidAIConfig.from_env({}), PaidAIConfig(enabled=False))

    def test_enabled_scenario_requires_attribution_and_budgets(self):
        with self.assertRaisesRegex(ValueError, "LOCUST_PAID_AI_OWNER"):
            PaidAIConfig.from_env({"LOCUST_PAID_AI_ENABLED": "true"})

    def test_enabled_scenario_parses_valid_controls(self):
        config = PaidAIConfig.from_env(
            {
                "LOCUST_PAID_AI_ENABLED": "true",
                "LOCUST_PAID_AI_OWNER": "nam",
                "LOCUST_PAID_AI_RUN_ID": "review-20260728",
                "LOCUST_PAID_AI_MAX_REQUESTS": "25",
                "LOCUST_PAID_AI_WINDOW_MINUTES": "10",
                "LOCUST_PAID_AI_WAIT_SECONDS": "3",
            }
        )

        self.assertTrue(config.enabled)
        self.assertEqual(config.owner, "nam")
        self.assertEqual(config.run_id, "review-20260728")
        self.assertEqual(config.max_requests, 25)
        self.assertEqual(config.window_seconds, 600)
        self.assertEqual(config.wait_seconds, 3)

    def test_request_cap_has_a_hard_ceiling(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 500"):
            PaidAIConfig.from_env(
                {
                    "LOCUST_PAID_AI_ENABLED": "true",
                    "LOCUST_PAID_AI_OWNER": "nam",
                    "LOCUST_PAID_AI_RUN_ID": "unsafe-run",
                    "LOCUST_PAID_AI_MAX_REQUESTS": "501",
                    "LOCUST_PAID_AI_WINDOW_MINUTES": "10",
                }
            )

    def test_wait_interval_rejects_non_finite_values(self):
        with self.assertRaisesRegex(ValueError, "finite and at least 1"):
            PaidAIConfig.from_env(
                {
                    "LOCUST_PAID_AI_ENABLED": "true",
                    "LOCUST_PAID_AI_OWNER": "nam",
                    "LOCUST_PAID_AI_RUN_ID": "unsafe-pacing",
                    "LOCUST_PAID_AI_MAX_REQUESTS": "10",
                    "LOCUST_PAID_AI_WINDOW_MINUTES": "10",
                    "LOCUST_PAID_AI_WAIT_SECONDS": "nan",
                }
            )


class PaidAIRequestBudgetTests(unittest.TestCase):
    def test_budget_stops_at_request_cap(self):
        config = PaidAIConfig(
            enabled=True,
            owner="nam",
            run_id="cap-test",
            max_requests=2,
            window_seconds=60,
        )
        budget = PaidAIRequestBudget(config, clock=lambda: 0)

        self.assertEqual(budget.claim(), (True, "allowed"))
        self.assertEqual(budget.claim(), (True, "allowed"))
        self.assertEqual(budget.claim(), (False, "request_cap_reached"))
        self.assertEqual(budget.request_count, 2)

    def test_budget_stops_when_window_elapses(self):
        now = [0.0]
        config = PaidAIConfig(
            enabled=True,
            owner="nam",
            run_id="window-test",
            max_requests=10,
            window_seconds=60,
        )
        budget = PaidAIRequestBudget(config, clock=lambda: now[0])
        budget.start()
        now[0] = 60.0

        self.assertEqual(budget.claim(), (False, "window_elapsed"))
        self.assertEqual(budget.request_count, 0)


class LocustScenarioIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(LOCUSTFILE.read_text(encoding="utf-8"))

    def test_baseline_user_has_no_paid_ai_route(self):
        website_user = _class_node(self.tree, "WebsiteUser")

        self.assertFalse(
            any(PAID_AI_ROUTE in value for value in _string_literals(website_user))
        )

    def test_paid_ai_user_is_defined_only_inside_enabled_gate(self):
        paid_ai_class = _class_node(self.tree, "PaidAIUser")
        parent_gate = next(
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.If) and paid_ai_class in node.body
        )

        self.assertEqual(ast.unparse(parent_gate.test), "paid_ai_config.enabled")
        self.assertTrue(
            any(PAID_AI_ROUTE in value for value in _string_literals(paid_ai_class))
        )

    def test_paid_ai_scenario_is_single_user(self):
        paid_ai_class = _class_node(self.tree, "PaidAIUser")
        fixed_count = next(
            node
            for node in paid_ai_class.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "fixed_count"
                for target in node.targets
            )
        )

        self.assertEqual(ast.literal_eval(fixed_count.value), 1)


if __name__ == "__main__":
    unittest.main()
