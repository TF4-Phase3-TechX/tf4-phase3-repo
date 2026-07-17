import os
import json
import unittest
from unittest.mock import patch
import importlib.util
import sys

base_dir = os.path.dirname(os.path.dirname(__file__))

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

llm_timeout_detector = load_module("llm_timeout_detector", os.path.join(base_dir, "w2-prototype", "llm_timeout_detector.py"))
LLMTimeoutDetector = llm_timeout_detector.LLMTimeoutDetector

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data
        
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP Error")

class TestTF4AIO45Validation(unittest.TestCase):
    @patch('requests.get')
    def test_tf4aio45_high_severity(self, mock_get):
        def mock_requests_get(url, *args, **kwargs):
            if "prometheus" in url:
                return MockResponse({
                    "status": "success",
                    "data": {
                        "result": [{"metric": {"__name__": "app_llm_errors_total"}, "value": [1600000000, "1.5"]}]
                    }
                })
            elif "opensearch" in url:
                return MockResponse({
                    "hits": {
                        "hits": [{"_source": {"message": "LLM connection timeout after 5000ms"}}]
                    }
                })
            return MockResponse({}, status_code=404)
        
        mock_get.side_effect = mock_requests_get
        
        detector = LLMTimeoutDetector()
        res = detector.detect(service="product-reviews", environment="production", tenant_id="default")
        
        print("\nDetection Result:")
        print(json.dumps(res, indent=2))
        
        self.assertEqual(res["severity"], "high", "Expected severity to be high")
        self.assertIn("metric_details", res["evidence"])
        self.assertIn("log_details", res["evidence"])

if __name__ == "__main__":
    unittest.main()
