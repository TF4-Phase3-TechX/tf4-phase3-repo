from metrics import init_metrics, llm_metric_identity


class FakeInstrument:
    def add(self, value, attributes=None):
        pass

    def record(self, value, attributes=None):
        pass


class FakeMeter:
    def __init__(self):
        self.names = []

    def create_counter(self, name, **kwargs):
        self.names.append(name)
        return FakeInstrument()

    def create_histogram(self, name, **kwargs):
        self.names.append(name)
        return FakeInstrument()


def test_pr131_metric_contract_is_preserved_for_bedrock():
    meter = FakeMeter()
    metrics = init_metrics(meter)

    assert {
        "app_llm_prompt_tokens_total",
        "app_llm_completion_tokens_total",
        "app_llm_estimated_cost_usd_total",
        "app_llm_latency_seconds",
        "app_llm_errors_total",
        "app_llm_calls_total",
    }.issubset(meter.names)
    assert {
        "app_llm_prompt_tokens_counter",
        "app_llm_completion_tokens_counter",
        "app_llm_estimated_cost_counter",
        "app_llm_latency_histogram",
        "app_llm_error_counter",
        "app_llm_call_counter",
    }.issubset(metrics)


def test_llm_metrics_carry_dynamic_caller_and_operation_labels():
    assert llm_metric_identity("shopping-copilot") == {
        "service.name": "shopping-copilot",
        "llm.operation": "ask_product_ai_assistant",
    }
