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


class FakeSNSClient:
    def __init__(self):
        self.publishes = []

    def publish(self, **kwargs):
        self.publishes.append(kwargs)
        return {'MessageId': 'fake-message-id'}


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
        cls.sns = FakeSNSClient()
        with patch('boto3.client', side_effect=[FakeSSMClient(), cls.cloudwatch, cls.sns]):
            cls.handler = importlib.import_module('handler')

    def setUp(self):
        self.cloudwatch.requests.clear()
        self.sns.publishes.clear()
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
        self.assertIn(
            'mandate11-ttd-test',
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

    def test_terraform_roles_only_bypass_exact_webhook_parameter_set(self):
        account = '511825856493'
        common = (
            account,
            'us-east-1',
            '192.0.2.20',
            'HashiCorp Terraform',
        )

        for role_name in (
            'tf4-github-actions-terraform-apply',
            'tf4-github-actions-plan',
        ):
            identity = {
                'arn': (
                    f'arn:aws:sts::{account}:assumed-role/'
                    f'{role_name}/GitHubActions'
                ),
            }
            with self.subTest(role=role_name):
                self.assertTrue(self.handler.is_expected_sensitive_read(
                    'GetParameter',
                    identity,
                    {'name': '/security-alerts/slack-webhook-url'},
                    *common,
                ))
                self.assertTrue(self.handler.is_expected_sensitive_read(
                    'GetParameters',
                    identity,
                    {'names': ['/security-alerts/slack-webhook-url']},
                    *common,
                ))
                self.assertFalse(self.handler.is_expected_sensitive_read(
                    'GetParameters',
                    identity,
                    {
                        'names': [
                            '/security-alerts/slack-webhook-url',
                            '/production/unapproved-parameter',
                        ],
                    },
                    *common,
                ))
                self.assertFalse(self.handler.is_expected_sensitive_read(
                    'GetParametersByPath',
                    identity,
                    {'path': '/security-alerts/'},
                    *common,
                ))

    def test_expected_reads_require_exact_service_role_and_resource(self):
        account = '511825856493'
        region = 'us-east-1'

        external_secrets = {
            'arn': (
                f'arn:aws:sts::{account}:assumed-role/'
                'external-secrets-techx-tf4-cluster/external-secrets'
            ),
        }
        self.assertTrue(self.handler.is_expected_sensitive_read(
            'GetSecretValue',
            external_secrets,
            {'secretId': 'techx/tf4/rds-postgres'},
            account,
            region,
            '192.0.2.21',
            'external-secrets',
        ))
        self.assertFalse(self.handler.is_expected_sensitive_read(
            'GetSecretValue',
            external_secrets,
            {'secretId': 'another-team/production-secret'},
            account,
            region,
            '192.0.2.21',
            'external-secrets',
        ))

        karpenter = {
            'arn': (
                f'arn:aws:sts::{account}:assumed-role/'
                'karpenter-controller-techx-tf4-cluster/controller'
            ),
        }
        self.assertTrue(self.handler.is_expected_sensitive_read(
            'GetParameter',
            karpenter,
            {'name': '/aws/service/eks/optimized-ami/1.33/amazon-linux-2023/x86_64/standard/recommended/image_id'},
            account,
            region,
            '192.0.2.22',
            'karpenter',
        ))
        self.assertFalse(self.handler.is_expected_sensitive_read(
            'GetParameter',
            karpenter,
            {'name': '/production/database-password'},
            account,
            region,
            '192.0.2.22',
            'karpenter',
        ))

    def test_resource_identifier_uses_only_event_specific_fields(self):
        self.assertEqual(
            self.handler.extract_resource_identifier(
                'AttachRolePolicy',
                {
                    'roleName': 'dms-vpc-role',
                    'policyArn': 'arn:aws:iam::aws:policy/service-role/AmazonDMSVPCManagementRole',
                    'unrelated': 'must-not-be-in-slack',
                },
            ),
            '{"policyArn":"arn:aws:iam::aws:policy/service-role/'
            'AmazonDMSVPCManagementRole","roleName":"dms-vpc-role"}',
        )
        self.assertEqual(
            self.handler.extract_resource_identifier(
                'GetSecretValue',
                {'secretId': 'techx/tf4/rds-postgres'},
            ),
            'techx/tf4/rds-postgres',
        )

    def test_msk_service_read_requires_exact_identity_and_secret_arn(self):
        account = '511825856493'
        region = 'us-east-1'
        identity = {
            'type': 'AWSService',
            'invokedBy': 'kafka.amazonaws.com',
        }
        secret = {
            'secretId': (
                f'arn:aws:secretsmanager:{region}:{account}:'
                'secret:AmazonMSK_techx_tf4_orders_app-test'
            ),
        }

        self.assertTrue(self.handler.is_expected_sensitive_read(
            'GetSecretValue',
            identity,
            secret,
            account,
            region,
            'kafka.amazonaws.com',
            'kafka.amazonaws.com',
        ))
        self.assertEqual(
            self.handler.extract_actor(identity),
            'kafka.amazonaws.com',
        )
        self.assertFalse(self.handler.is_expected_sensitive_read(
            'GetSecretValue',
            identity,
            {'secretId': f'arn:aws:secretsmanager:{region}:{account}:secret:other'},
            account,
            region,
            'kafka.amazonaws.com',
            'kafka.amazonaws.com',
        ))
        self.assertFalse(self.handler.is_expected_sensitive_read(
            'GetSecretValue',
            {'type': 'AssumedRole', 'invokedBy': 'kafka.amazonaws.com'},
            secret,
            account,
            region,
            'kafka.amazonaws.com',
            'kafka.amazonaws.com',
        ))

    def test_dms_read_requires_exact_role_session_and_secret(self):
        account = '511825856493'
        region = 'us-east-1'
        identity = {
            'type': 'AssumedRole',
            'arn': (
                f'arn:aws:sts::{account}:assumed-role/'
                'techx-tf4-postgresql-dms-secrets-access/'
                'dms-session-for-replication-engine'
            ),
        }
        common = (account, region, '18.204.125.157', 'aws-sdk-go-v2')

        for secret_name in (
            'techx/tf4/dms-postgres-source-CeiU4M',
            'techx/tf4/rds-postgres-T586rF',
        ):
            with self.subTest(secret=secret_name):
                self.assertTrue(self.handler.is_expected_sensitive_read(
                    'GetSecretValue',
                    identity,
                    {
                        'secretId': (
                            f'arn:aws:secretsmanager:{region}:{account}:'
                            f'secret:{secret_name}'
                        ),
                    },
                    *common,
                ))

        self.assertFalse(self.handler.is_expected_sensitive_read(
            'GetSecretValue',
            identity,
            {
                'secretId': (
                    f'arn:aws:secretsmanager:{region}:{account}:'
                    'secret:techx/tf4/openai-test'
                ),
            },
            *common,
        ))
        wrong_session = dict(identity)
        wrong_session['arn'] = wrong_session['arn'].replace(
            'dms-session-for-replication-engine',
            'unexpected-session',
        )
        self.assertFalse(self.handler.is_expected_sensitive_read(
            'GetSecretValue',
            wrong_session,
            {
                'secretId': (
                    f'arn:aws:secretsmanager:{region}:{account}:'
                    'secret:techx/tf4/rds-postgres-T586rF'
                ),
            },
            *common,
        ))

    def test_public_postgresql_ingress_remains_alertable(self):
        event_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        request_params = {
            'ipPermissions': {
                'items': [{
                    'ipProtocol': 'tcp',
                    'fromPort': 5432,
                    'toPort': 5432,
                    'ipRanges': {'items': [{'cidrIp': '0.0.0.0/0'}]},
                }],
            },
        }

        self.assertTrue(self.handler.is_public_sg_ingress(request_params))

        cloudtrail_event = {
            'source': 'aws.ec2',
            'detail-type': 'AWS API Call via CloudTrail',
            'account': '511825856493',
            'region': 'us-east-1',
            'time': event_time.isoformat().replace('+00:00', 'Z'),
            'detail': {
                'eventID': 'eeeeeeee-ffff-0000-1111-222222222222',
                'eventName': 'AuthorizeSecurityGroupIngress',
                'eventTime': event_time.isoformat().replace('+00:00', 'Z'),
                'sourceIPAddress': '18.204.125.157',
                'userIdentity': {
                    'arn': (
                        'arn:aws:sts::511825856493:assumed-role/'
                        'AmazonEKSLoadBalancerControllerRole/controller'
                    ),
                },
                'requestParameters': request_params,
            },
        }
        sns_event = {
            'Records': [{'Sns': {'Message': json.dumps(cloudtrail_event)}}]
        }

        with patch.object(
            self.handler.urllib.request,
            'urlopen',
            return_value=FakeHTTPResponse(),
        ) as urlopen:
            self.handler.lambda_handler(sns_event, None)

        urlopen.assert_called_once()
        self.assertIn(
            'AuthorizeSecurityGroupIngress',
            urlopen.call_args.args[0].data.decode('utf-8'),
        )

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

    def test_formatted_email_published_before_slack_for_real_alert(self):
        """publish_formatted_email is called with correct fields for a real alert."""
        os.environ['FORMATTED_SNS_TOPIC_ARN'] = 'arn:aws:sns:us-east-1:511825856493:audit-security-alerts-formatted'
        self.handler.FORMATTED_SNS_TOPIC_ARN = os.environ['FORMATTED_SNS_TOPIC_ARN']

        event_time = datetime.now(timezone.utc) - timedelta(seconds=8)
        cloudtrail_event = {
            'source': 'aws.iam',
            'detail-type': 'AWS API Call via CloudTrail',
            'account': '511825856493',
            'region': 'us-east-1',
            'time': event_time.isoformat().replace('+00:00', 'Z'),
            'detail': {
                'eventID': 'ffffffff-0000-1111-2222-333333333333',
                'eventName': 'CreateAccessKey',
                'eventTime': event_time.isoformat().replace('+00:00', 'Z'),
                'sourceIPAddress': '1.2.3.4',
                'userIdentity': {
                    'arn': 'arn:aws:sts::511825856493:assumed-role/TF4-Test/attacker',
                },
                'requestParameters': {
                    'userName': 'test-backdoor-user',
                },
            },
        }
        sns_event = {
            'Records': [{'Sns': {'Message': json.dumps(cloudtrail_event)}}]
        }

        with patch.object(
            self.handler.urllib.request,
            'urlopen',
            return_value=FakeHTTPResponse(),
        ):
            self.handler.lambda_handler(sns_event, None)

        # SNS publish must have been called exactly once
        self.assertEqual(len(self.sns.publishes), 1)
        publish_call = self.sns.publishes[0]

        self.assertEqual(
            publish_call['TopicArn'],
            'arn:aws:sns:us-east-1:511825856493:audit-security-alerts-formatted',
        )
        # Subject must not exceed SNS 100-character limit
        self.assertLessEqual(len(publish_call['Subject']), 100)
        self.assertIn('CreateAccessKey', publish_call['Subject'])
        self.assertIn('HIGH', publish_call['Subject'])

        # Body must contain key alert fields
        body = publish_call['Message']
        self.assertIn('CreateAccessKey', body)
        self.assertIn('HIGH', body)
        self.assertIn('1.2.3.4', body)
        self.assertIn('test-backdoor-user', body)
        self.assertIn('ffffffff-0000-1111-2222-333333333333', body)

    def test_email_failure_does_not_block_slack(self):
        """If SNS publish raises, the Slack notification must still be sent."""
        os.environ['FORMATTED_SNS_TOPIC_ARN'] = 'arn:aws:sns:us-east-1:511825856493:audit-security-alerts-formatted'
        self.handler.FORMATTED_SNS_TOPIC_ARN = os.environ['FORMATTED_SNS_TOPIC_ARN']

        event_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        cloudtrail_event = {
            'source': 'aws.cloudtrail',
            'detail-type': 'AWS API Call via CloudTrail',
            'account': '511825856493',
            'region': 'us-east-1',
            'time': event_time.isoformat().replace('+00:00', 'Z'),
            'detail': {
                'eventID': 'aaaabbbb-cccc-dddd-eeee-ffffffffffff',
                'eventName': 'StopLogging',
                'eventTime': event_time.isoformat().replace('+00:00', 'Z'),
                'sourceIPAddress': '5.6.7.8',
                'userIdentity': {
                    'arn': 'arn:aws:sts::511825856493:assumed-role/TF4-Test/attacker',
                },
            },
        }
        sns_event = {
            'Records': [{'Sns': {'Message': json.dumps(cloudtrail_event)}}]
        }

        # Make SNS publish raise an exception
        original_publish = self.handler.sns_client.publish
        call_count = {'slack': 0}

        def failing_publish(**kwargs):
            raise Exception("SNS service unavailable")

        self.handler.sns_client.publish = failing_publish

        try:
            with patch.object(
                self.handler.urllib.request,
                'urlopen',
                return_value=FakeHTTPResponse(),
            ) as urlopen:
                # Must NOT raise despite SNS failure
                self.handler.lambda_handler(sns_event, None)

            # Slack must still have been called
            urlopen.assert_called_once()
            slack_payload = urlopen.call_args.args[0].data.decode('utf-8')
            self.assertIn('StopLogging', slack_payload)
        finally:
            self.handler.sns_client.publish = original_publish


if __name__ == '__main__':
    unittest.main()
