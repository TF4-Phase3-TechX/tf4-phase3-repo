import json
from unittest.mock import patch
from llm_timeout_detector import LLMTimeoutDetector

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data
        
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP Error")

def test_high_severity():
    with patch('requests.get') as mock_get:
        def mock_requests_get(url, *args, **kwargs):
            if "prometheus" in url:
                return MockResponse({
                    "status": "success",
                    "data": {
                        "result": [{"metric": {"__name__": "app_llm_requests_total"}, "value": [1600000000, "1.5"]}]
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
        return res

if __name__ == "__main__":
    print("Running validation test for LLM Timeout/Error signal...")
    result = test_high_severity()
    print("Detection Result:")
    print(json.dumps(result, indent=2))
    assert result["severity"] == "high", "Expected severity to be high"
    print("\nValidation SUCCESS: Detector successfully recognized simulated AI-path timeout/error.")
