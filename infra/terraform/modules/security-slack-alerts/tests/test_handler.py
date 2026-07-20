import importlib
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


class FakeSSMClient:
    def get_parameter(self, **kwargs):
        return {'Parameter': {'Value': 'https://hooks.slack.com/services/test'}}


class FakeCloudWatchClient:
    def __init__(self):
        self.requests = []

    def put_metric_data(self, **kwargs):
        self.requests.append(kwargs)


class FakeHTTPResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class HandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lambda_src = Path(__file__).resolve().parents[1] / 'lambda_src'
        sys.path.insert(0, str(lambda_src))
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        os.environ['AWS_EC2_METADATA_DISABLED'] = 'true'

        cls.cloudwatch = FakeCloudWatchClient()
        with patch('boto3.client', side_effect=[FakeSSMClient(), cls.cloudwatch]):
            cls.handler = importlib.import_module('handler')

    def setUp(self):
        self.cloudwatch.requests.clear()
        self.handler.WEBHOOK_URL = None

    def test_calculate_latency_accepts_cloudtrail_fractional_timestamp(self):
        observed_at = datetime(2026, 7, 18, 1, 0, 12, 450000, tzinfo=timezone.utc)
        latency = self.handler.calculate_latency_seconds(
            '2026-07-18T01:00:00.000Z',
            observed_at,
        )

        self.assertEqual(latency, 12.45)

    def test_handler_publishes_detection_and_notification_metrics(self):
        event_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        cloudtrail_event = {
            'source': 'aws.iam',
            'detail-type': 'AWS API Call via CloudTrail',
            'account': '511825856493',
            'region': 'us-east-1',
            # This intentionally differs from detail.eventTime. The handler must
            # use the original CloudTrail timestamp for TTD.
            'time': (event_time - timedelta(hours=1)).isoformat().replace('+00:00', 'Z'),
            'detail': {
                'eventID': '11111111-2222-3333-4444-555555555555',
                'eventName': 'CreateUser',
                'eventTime': event_time.isoformat().replace('+00:00', 'Z'),
                'sourceIPAddress': '192.0.2.10',
                'userIdentity': {
                    'arn': 'arn:aws:sts::511825856493:assumed-role/TF4-Test/mentor',
                },
                'requestParameters': {
                    'userName': 'mandate11-ttd-test',
                },
            },
        }
        sns_event = {
            'Records': [
                {
                    'Sns': {
                        'Message': json.dumps(cloudtrail_event),
                    }
                }
            ]
        }

        with patch.object(
            self.handler.urllib.request,
            'urlopen',
            return_value=FakeHTTPResponse(),
        ) as urlopen:
            self.handler.lambda_handler(sns_event, None)

        urlopen.assert_called_once()
        slack_request = urlopen.call_args.args[0]
        self.assertIn(
            '11111111-2222-3333-4444-555555555555',
            slack_request.data.decode('utf-8'),
        )
        self.assertEqual(len(self.cloudwatch.requests), 1)
        request = self.cloudwatch.requests[0]
        self.assertEqual(request['Namespace'], 'Mandate11/DetectionLatency')

        metrics = {metric['MetricName']: metric for metric in request['MetricData']}
        self.assertEqual(
            set(metrics),
            {'DetectionLatencySeconds', 'NotificationLatencySeconds'},
        )
        for metric in metrics.values():
            self.assertEqual(metric['Unit'], 'Seconds')
            self.assertEqual(
                metric['Dimensions'],
                [{'Name': 'Pipeline', 'Value': 'CloudTrailToSlack'}],
            )
            self.assertGreaterEqual(metric['Value'], 9)
            self.assertLess(metric['Value'], 30)

    def test_github_actions_actor_does_not_bypass_critical_alert(self):
        event_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        cloudtrail_event = {
            'source': 'aws.cloudtrail',
            'detail-type': 'AWS API Call via CloudTrail',
            'account': '511825856493',
            'region': 'us-east-1',
            'time': event_time.isoformat().replace('+00:00', 'Z'),
            'detail': {
                'eventID': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                'eventName': 'StopLogging',
                'eventTime': event_time.isoformat().replace('+00:00', 'Z'),
                'sourceIPAddress': '192.0.2.11',
                'userIdentity': {
                    'arn': (
                        'arn:aws:sts::511825856493:assumed-role/'
                        'tf4-github-actions/test-session'
                    ),
                },
            },
        }
        sns_event = {
            'Records': [
                {'Sns': {'Message': json.dumps(cloudtrail_event)}}
            ]
        }

        with patch.object(
            self.handler.urllib.request,
            'urlopen',
            return_value=FakeHTTPResponse(),
        ) as urlopen:
            self.handler.lambda_handler(sns_event, None)

        urlopen.assert_called_once()
        slack_payload = urlopen.call_args.args[0].data.decode('utf-8')
        self.assertIn('StopLogging', slack_payload)
        self.assertIn('CRITICAL', slack_payload)
        self.assertEqual(len(self.cloudwatch.requests), 1)

    def test_alert_lambda_webhook_read_is_filtered(self):
        event_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        cloudtrail_event = {
            'source': 'aws.ssm',
            'detail-type': 'AWS API Call via CloudTrail',
            'account': '511825856493',
            'region': 'us-east-1',
            'time': event_time.isoformat().replace('+00:00', 'Z'),
            'detail': {
                'eventID': 'bbbbbbbb-cccc-dddd-eeee-ffffffffffff',
                'eventName': 'GetParameter',
                'eventTime': event_time.isoformat().replace('+00:00', 'Z'),
                'sourceIPAddress': '192.0.2.12',
                'userIdentity': {
                    'arn': (
                        'arn:aws:sts::511825856493:assumed-role/'
                        'SecuritySlackAlertsLambdaRole/'
                        'audit-security-slack-alerts'
                    ),
                },
                'requestParameters': {
                    'name': '/security-alerts/slack-webhook-url',
                },
            },
        }
        sns_event = {
            'Records': [
                {'Sns': {'Message': json.dumps(cloudtrail_event)}}
            ]
        }

        with patch.object(self.handler.urllib.request, 'urlopen') as urlopen:
            self.handler.lambda_handler(sns_event, None)

        urlopen.assert_not_called()
        self.assertEqual(self.cloudwatch.requests, [])

    def test_github_actions_only_bypasses_exact_webhook_parameter(self):
        event_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        cloudtrail_event = {
            'source': 'aws.ssm',
            'detail-type': 'AWS API Call via CloudTrail',
            'account': '511825856493',
            'region': 'us-east-1',
            'time': event_time.isoformat().replace('+00:00', 'Z'),
            'detail': {
                'eventID': 'cccccccc-dddd-eeee-ffff-000000000000',
                'eventName': 'GetParameter',
                'eventTime': event_time.isoformat().replace('+00:00', 'Z'),
                'sourceIPAddress': '192.0.2.13',
                'userIdentity': {
                    'arn': (
                        'arn:aws:sts::511825856493:assumed-role/'
                        'tf4-github-actions-terraform-apply/test-session'
                    ),
                },
                'requestParameters': {
                    'name': '/production/unapproved-sensitive-parameter',
                },
            },
        }
        sns_event = {
            'Records': [
                {'Sns': {'Message': json.dumps(cloudtrail_event)}}
            ]
        }

        with patch.object(
            self.handler.urllib.request,
            'urlopen',
            return_value=FakeHTTPResponse(),
        ) as urlopen:
            self.handler.lambda_handler(sns_event, None)

        urlopen.assert_called_once()
        self.assertEqual(len(self.cloudwatch.requests), 1)

    def test_slack_failure_is_retried_and_does_not_emit_notification_metric(self):
        event_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        cloudtrail_event = {
            'source': 'aws.iam',
            'detail-type': 'AWS API Call via CloudTrail',
            'account': '511825856493',
            'region': 'us-east-1',
            'time': event_time.isoformat().replace('+00:00', 'Z'),
            'detail': {
                'eventID': 'dddddddd-eeee-ffff-0000-111111111111',
                'eventName': 'CreateUser',
                'eventTime': event_time.isoformat().replace('+00:00', 'Z'),
                'sourceIPAddress': '192.0.2.14',
                'userIdentity': {
                    'arn': 'arn:aws:sts::511825856493:assumed-role/TF4-Test/mentor',
                },
            },
        }
        sns_event = {
            'Records': [
                {'Sns': {'Message': json.dumps(cloudtrail_event)}}
            ]
        }

        with patch.object(
            self.handler.urllib.request,
            'urlopen',
            side_effect=self.handler.urllib.error.URLError('timeout'),
        ):
            with self.assertRaises(self.handler.urllib.error.URLError):
                self.handler.lambda_handler(sns_event, None)

        self.assertEqual(len(self.cloudwatch.requests), 1)
        metric_names = {
            metric['MetricName']
            for metric in self.cloudwatch.requests[0]['MetricData']
        }
        self.assertEqual(metric_names, {'DetectionLatencySeconds'})

    def test_webhook_url_requires_https_and_approved_host(self):
        with self.assertRaises(ValueError):
            self.handler.validate_webhook_url('http://hooks.slack.com/services/test')
        with self.assertRaises(ValueError):
            self.handler.validate_webhook_url('https://example.com/webhook')

        valid = 'https://hooks.slack.com/services/test'
        self.assertEqual(self.handler.validate_webhook_url(valid), valid)


if __name__ == '__main__':
    unittest.main()
