import json
import os
import urllib.error
import urllib.parse
import urllib.request
import logging
import boto3
from datetime import datetime, timedelta, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm_client = boto3.client('ssm')
cloudwatch_client = boto3.client('cloudwatch')
WEBHOOK_URL = None
METRIC_NAMESPACE = os.environ.get('DETECTION_METRIC_NAMESPACE', 'Mandate11/DetectionLatency')
DETECTION_TARGET_SECONDS = float(os.environ.get('DETECTION_LATENCY_TARGET_SECONDS', '60'))
SLACK_ALERT_LAMBDA_ROLE = 'SecuritySlackAlertsLambdaRole'
TERRAFORM_APPLY_ROLE = 'tf4-github-actions-terraform-apply'
TERRAFORM_PLAN_ROLE = 'tf4-github-actions-plan'
EXTERNAL_SECRETS_ROLE = 'external-secrets-techx-tf4-cluster'
KARPENTER_CONTROLLER_ROLE = 'karpenter-controller-techx-tf4-cluster'
KARPENTER_PUBLIC_PARAMETER_PREFIX = '/aws/service/eks/optimized-ami/'
SENSITIVE_READ_EVENTS = {
    'GetSecretValue',
    'GetParameter',
    'GetParameters',
    'GetParametersByPath',
}
CRITICAL_EVENTS = {
    'ConsoleLogin',
    'StopLogging',
    'DeleteTrail',
    'UpdateTrail',
    'PutEventSelectors',
    'DeleteConfigurationRecorder',
    'StopConfigurationRecorder',
    'DeleteDeliveryChannel',
    'PutConfigurationRecorder',
    'PutDeliveryChannel',
    'CreateAccessEntry',
    'AssociateAccessPolicy',
}
ALLOWED_SLACK_WEBHOOK_HOSTS = {
    host.strip().lower()
    for host in os.environ.get(
        'SLACK_WEBHOOK_ALLOWED_HOSTS',
        'hooks.slack.com',
    ).split(',')
    if host.strip()
}


def parse_aws_timestamp(value):
    if not value or value == 'UnknownTime':
        return None

    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        logger.warning(f"Could not parse AWS timestamp {value}: {exc}")
        return None


def calculate_latency_seconds(event_time, observed_at):
    event_dt = parse_aws_timestamp(event_time)
    if event_dt is None:
        return None

    latency_seconds = (observed_at - event_dt).total_seconds()
    if latency_seconds < -5:
        logger.warning(
            f"Ignoring negative latency {latency_seconds:.3f}s for event time {event_time}; "
            "check clock synchronization and event payload"
        )
        return None

    return max(0.0, latency_seconds)


def publish_latency_metrics(metrics, pipeline, event_id, event_name, event_time):
    metric_data = []
    for metric_name, latency_seconds, observed_at in metrics:
        if latency_seconds is None:
            continue
        metric_data.append({
            'MetricName': metric_name,
            'Dimensions': [
                {
                    'Name': 'Pipeline',
                    'Value': pipeline,
                }
            ],
            'Timestamp': observed_at,
            'Value': latency_seconds,
            'Unit': 'Seconds',
        })

    if not metric_data:
        return

    try:
        cloudwatch_client.put_metric_data(
            Namespace=METRIC_NAMESPACE,
            MetricData=metric_data,
        )
        for metric in metric_data:
            logger.info(json.dumps({
                'marker': 'MANDATE11_TTD',
                'namespace': METRIC_NAMESPACE,
                'metricName': metric['MetricName'],
                'pipeline': pipeline,
                'eventId': event_id,
                'eventName': event_name,
                'eventTime': event_time,
                'observedAt': metric['Timestamp'].isoformat(),
                'latencySeconds': round(metric['Value'], 3),
            }))
    except Exception as exc:
        # Metric publication must never suppress the security notification path.
        logger.error(f"Failed to publish detection latency metrics: {exc}")


def validate_webhook_url(webhook_url):
    parsed = urllib.parse.urlparse(webhook_url)
    if (
        parsed.scheme != 'https'
        or not parsed.hostname
        or parsed.hostname.lower() not in ALLOWED_SLACK_WEBHOOK_HOSTS
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "Slack webhook URL must use HTTPS and an approved Slack host"
        )
    return webhook_url


def get_webhook_url():
    global WEBHOOK_URL
    if WEBHOOK_URL:
        return WEBHOOK_URL
        
    param_name = os.environ.get('SLACK_WEBHOOK_SSM_PARAM')
    try:
        response = ssm_client.get_parameter(
            Name=param_name,
            WithDecryption=True
        )
        WEBHOOK_URL = validate_webhook_url(response['Parameter']['Value'])
        return WEBHOOK_URL
    except Exception as e:
        logger.error(f"Failed to fetch SSM parameter {param_name}: {e}")
        raise

def is_public_sg_ingress(request_params):
    if not request_params:
        return False
        
    ip_permissions = request_params.get('ipPermissions', {}).get('items', [])
    for perm in ip_permissions:
        ip_ranges = perm.get('ipRanges', {}).get('items', [])
        for ip_range in ip_ranges:
            cidr = ip_range.get('cidrIp')
            if cidr in ['0.0.0.0/0', '::/0']:
                return True
                
        ipv6_ranges = perm.get('ipv6Ranges', {}).get('items', [])
        for ip_range in ipv6_ranges:
            cidr = ip_range.get('cidrIpv6')
            if cidr in ['0.0.0.0/0', '::/0']:
                return True
    return False

def is_public_bucket_policy(request_params):
    if not request_params:
        return False
    
    bucket_policy = request_params.get('bucketPolicy', {})
    if isinstance(bucket_policy, str):
        try:
            bucket_policy = json.loads(bucket_policy)
        except Exception:
            return False

    statements = bucket_policy.get('Statement', [])
    if isinstance(statements, dict):
        statements = [statements]

    for stmt in statements:
        effect = stmt.get('Effect', '')
        if effect != 'Allow':
            continue

        principal = stmt.get('Principal', {})
        if principal == '*' or (isinstance(principal, dict) and principal.get('AWS') == '*'):
            # It's a public policy, but wait, does it have conditions?
            # A strict check would also look for 'Condition'.
            # To be safe, if there's no condition, it is highly likely public.
            if not stmt.get('Condition'):
                return True

    return False


def extract_actor(user_identity):
    return (
        user_identity.get('arn')
        or user_identity.get('principalId')
        or user_identity.get('invokedBy')
        or user_identity.get('type')
        or 'UnknownActor'
    )


def extract_resource_identifier(event_name, request_params):
    request_params = request_params or {}
    event_fields = {
        'CreateUser': ('userName',),
        'CreateAccessKey': ('userName',),
        'CreateRole': ('roleName',),
        'AttachRolePolicy': ('roleName', 'policyArn'),
        'PutRolePolicy': ('roleName', 'policyName'),
        'UpdateAssumeRolePolicy': ('roleName',),
        'CreateAccessEntry': ('name', 'principalArn'),
        'AssociateAccessPolicy': ('name', 'principalArn', 'policyArn'),
        'AuthorizeSecurityGroupIngress': ('groupId',),
        'PutBucketPolicy': ('bucketName',),
        'PutBucketAcl': ('bucketName',),
        'DeleteConfigurationRecorder': ('configurationRecorderName',),
        'StopConfigurationRecorder': ('configurationRecorderName',),
        'DeleteDeliveryChannel': ('deliveryChannelName',),
        'PutConfigurationRecorder': ('configurationRecorder',),
        'PutDeliveryChannel': ('deliveryChannel',),
    }
    fallback_fields = (
        'secretId',
        'name',
        'names',
        'path',
        'trailName',
        'resourceArn',
    )
    fields = event_fields.get(event_name, fallback_fields)
    resource = {
        field: request_params[field]
        for field in fields
        if request_params.get(field) not in (None, '', [], {})
    }
    if not resource:
        return 'UnknownResource'
    if len(resource) == 1:
        value = next(iter(resource.values()))
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(',', ':'), sort_keys=True)[:500]
        return str(value)[:500]
    return json.dumps(resource, separators=(',', ':'), sort_keys=True)[:500]


def is_exact_assumed_role(actor, account, role_name):
    arn_parts = actor.split(':', 5)
    if len(arn_parts) != 6:
        return False

    resource_parts = arn_parts[5].split('/', 2)
    return (
        arn_parts[2] == 'sts'
        and arn_parts[4] == account
        and len(resource_parts) == 3
        and resource_parts[0] == 'assumed-role'
        and resource_parts[1] == role_name
        and bool(resource_parts[2])
    )


def requested_ssm_parameters(event_name, request_params):
    request_params = request_params or {}
    if event_name == 'GetParameter':
        names = [request_params.get('name')]
    elif event_name == 'GetParameters':
        names = request_params.get('names', [])
        if isinstance(names, str):
            names = [names]
    elif event_name == 'GetParametersByPath':
        names = [request_params.get('path')]
    else:
        names = []

    return [name for name in names if isinstance(name, str) and name]


def secret_matches_prefix(secret_id, account, region, prefix):
    if not isinstance(secret_id, str):
        return False
    return (
        secret_id.startswith(prefix)
        or secret_id.startswith(
            f'arn:aws:secretsmanager:{region}:{account}:secret:{prefix}'
        )
    )


def is_expected_sensitive_read(
    event_name,
    user_identity,
    request_params,
    account,
    region,
    source_ip,
    user_agent,
):
    request_params = request_params or {}
    actor = extract_actor(user_identity)
    webhook_parameter = os.environ.get(
        'SLACK_WEBHOOK_SSM_PARAM',
        '/security-alerts/slack-webhook-url',
    )

    if event_name in ('GetParameter', 'GetParameters', 'GetParametersByPath'):
        parameter_names = requested_ssm_parameters(event_name, request_params)
        reads_only_webhook = (
            event_name in ('GetParameter', 'GetParameters')
            and bool(parameter_names)
            and all(name == webhook_parameter for name in parameter_names)
        )

        if is_exact_assumed_role(
            actor,
            account,
            SLACK_ALERT_LAMBDA_ROLE,
        ):
            return event_name == 'GetParameter' and reads_only_webhook

        if any(
            is_exact_assumed_role(actor, account, role_name)
            for role_name in (TERRAFORM_APPLY_ROLE, TERRAFORM_PLAN_ROLE)
        ):
            return reads_only_webhook

        if is_exact_assumed_role(
            actor,
            account,
            KARPENTER_CONTROLLER_ROLE,
        ):
            return (
                event_name == 'GetParameter'
                and bool(parameter_names)
                and all(
                    name.startswith(KARPENTER_PUBLIC_PARAMETER_PREFIX)
                    for name in parameter_names
                )
            )

        return False

    if event_name == 'GetSecretValue':
        secret_id = request_params.get('secretId', '')
        external_secrets_read = (
            is_exact_assumed_role(
                actor,
                account,
                EXTERNAL_SECRETS_ROLE,
            )
            and secret_matches_prefix(
                secret_id,
                account,
                region,
                'techx/tf4/',
            )
        )
        msk_service_read = (
            user_identity.get('type') == 'AWSService'
            and user_identity.get('invokedBy') == 'kafka.amazonaws.com'
            and source_ip == 'kafka.amazonaws.com'
            and user_agent == 'kafka.amazonaws.com'
            and isinstance(secret_id, str)
            and secret_id.startswith(
                f'arn:aws:secretsmanager:{region}:{account}:'
                'secret:AmazonMSK_'
            )
        )
        return external_secrets_read or msk_service_read

    return False

def lambda_handler(event, context):
    logger.info(json.dumps({
        'marker': 'SECURITY_ALERT_BATCH_RECEIVED',
        'recordCount': len(event.get('Records', [])),
        'requestId': getattr(context, 'aws_request_id', None),
    }))
    
    for record in event.get('Records', []):
        sns_message = record.get('Sns', {}).get('Message')
        if not sns_message:
            continue
            
        try:
            message = json.loads(sns_message)
        except json.JSONDecodeError:
            logger.error("SNS Message is not valid JSON")
            continue

        lambda_received_at = datetime.now(timezone.utc)
        source = message.get('source')
        detail = message.get('detail', {})
        
        event_id = detail.get('eventID') or detail.get('id', 'UnknownEventID')
        event_name = "UnknownEvent"
        actor = "UnknownActor"
        resource_identifier = "UnknownResource"
        account = message.get('account', 'UnknownAccount')
        region = message.get('region', 'UnknownRegion')
        timestamp = detail.get('eventTime') or message.get('time', 'UnknownTime')
        source_ip = "UnknownIP"
        severity = "high"
        metric_pipeline = 'UnknownToSlack'
        
        should_alert = True
        
        if message.get('detail-type') in ('AWS API Call via CloudTrail', 'AWS Console Sign In via CloudTrail'):
            metric_pipeline = 'CloudTrailToSlack'
            event_name = detail.get('eventName', 'UnknownEvent')
            user_identity = detail.get('userIdentity', {})
            actor = extract_actor(user_identity)
            source_ip = detail.get('sourceIPAddress', 'UnknownIP')
            user_agent = detail.get('userAgent', '')
            request_params = detail.get('requestParameters', {})
            resource_identifier = extract_resource_identifier(
                event_name,
                request_params,
            )
            if is_expected_sensitive_read(
                event_name,
                user_identity,
                request_params,
                account,
                region,
                source_ip,
                user_agent,
            ):
                should_alert = False
                logger.info(json.dumps({
                    'marker': 'MANDATE11_EXPECTED_READ',
                    'eventName': event_name,
                    'actor': actor,
                    'resource': resource_identifier,
                    'reason': 'exact_identity_api_resource_allowlist',
                }))
            elif event_name == 'AuthorizeSecurityGroupIngress':
                if not is_public_sg_ingress(detail.get('requestParameters')):
                    should_alert = False
                    logger.info("Ignoring AuthorizeSecurityGroupIngress as it is not public (0.0.0.0/0 or ::/0).")
            elif event_name in ['PutBucketPolicy', 'PutBucketAcl']:
                # Very basic check, should ideally parse fully
                if 'AccessControlPolicy' in request_params:
                    # PutBucketAcl
                    acl_str = str(request_params.get('AccessControlPolicy')).lower()
                    if 'allusers' not in acl_str and 'authenticatedusers' not in acl_str:
                         should_alert = False
                         logger.info("Ignoring PutBucketAcl as it is not granting public access.")
                elif 'bucketPolicy' in request_params:
                    # PutBucketPolicy
                     if not is_public_bucket_policy(request_params):
                         should_alert = False
                         logger.info("Ignoring PutBucketPolicy as it may not be public.")
                         
            if event_name in CRITICAL_EVENTS:
                severity = "critical"
                
        elif source == 'aws.access-analyzer':
            metric_pipeline = 'AccessAnalyzerToSlack'
            event_name = "AccessAnalyzerFinding"
            actor = "AccessAnalyzer"
            severity = "critical"
            # Extract finding details if needed
            finding_id = detail.get('id', 'UnknownID')
            event_name = f"AccessAnalyzer Finding: {finding_id}"
            resource_identifier = detail.get('resource', 'UnknownResource')
            
        else:
             logger.warning(f"Unknown source: {source}")
             
        if not should_alert:
            continue
        short_actor = actor
        if actor and '/' in actor:
            short_actor = actor.split('/')[-1]

        if (
            event_name not in SENSITIVE_READ_EVENTS
            and is_exact_assumed_role(actor, account, TERRAFORM_APPLY_ROLE)
        ):
            noise_check = (
                "Privileged write từ CI/CD: vẫn cảnh báo để phát hiện "
                "pipeline bị chiếm quyền"
            )
        else:
            noise_check = (
                "Không khớp allowlist identity + API + resource → cảnh báo thật"
            )

        detection_latency = calculate_latency_seconds(timestamp, lambda_received_at)
        latency_msg = "Unknown"
        display_time = timestamp
        if detection_latency is not None:
            sample_status = "WITHIN TARGET" if detection_latency < DETECTION_TARGET_SECONDS else "ABOVE TARGET"
            latency_msg = (
                f"{detection_latency:.2f} giây ({sample_status}; "
                f"mục tiêu p95 < {DETECTION_TARGET_SECONDS:.0f} giây)"
            )

        event_dt = parse_aws_timestamp(timestamp)
        if event_dt is not None:
            event_dt_vn = event_dt + timedelta(hours=7)
            display_time = (
                f"{event_dt_vn.strftime('%Y-%m-%d %H:%M:%S')} +07 "
                f"(UTC: {timestamp})"
            )

        cloudtrail_link = f"https://{region}.console.aws.amazon.com/cloudtrail/home?region={region}#/events?EventName={event_name}"
        if message.get('detail-type') not in ('AWS API Call via CloudTrail', 'AWS Console Sign In via CloudTrail'):
            cloudtrail_link = "N/A"
            
        runbook_link = "https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/audit/runbooks/mandate-11-incident-response.md"
            
        # Build Slack Message (Block Kit)
        color = "#ff0000" if severity == "critical" else "#ff9900"
        slack_message = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"🚨 Security Alert: {event_name}",
                                "emoji": True
                            }
                        },
                        {
                            "type": "section",
                            "fields": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Actor:*\n*{short_actor}*\n`{actor}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Time:*\n{display_time}"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Account:*\n`{account}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Region:*\n`{region}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Severity:*\n`{severity.upper()}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Event ID:*\n`{event_id}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Detection latency:*\n`{latency_msg}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Resource:*\n`{resource_identifier}`"
                                }
                            ]
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Source IP:* `{source_ip}`\n*Noise check:* {noise_check}\n*Investigate:* <{cloudtrail_link}|View in CloudTrail> | *Runbook:* <{runbook_link}|Security Runbook>"
                            }
                        }
                    ]
                }
            ]
        }
        
        # Send to Slack
        webhook_url = get_webhook_url()
        req = urllib.request.Request(
            webhook_url, 
            data=json.dumps(slack_message).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        
        notification_latency = None
        slack_accepted_at = None
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                slack_accepted_at = datetime.now(timezone.utc)
                notification_latency = calculate_latency_seconds(timestamp, slack_accepted_at)
                logger.info(f"Message accepted by Slack webhook. Response status: {response.status}")
        except urllib.error.HTTPError as e:
            logger.error(f"Failed to send message to Slack. HTTP Error: {e.code} - {e.read().decode('utf-8')}")
            raise
        except urllib.error.URLError as e:
            logger.error(f"Failed to send message to Slack. URL Error: {e.reason}")
            raise
        finally:
            publish_latency_metrics(
                [
                    ('DetectionLatencySeconds', detection_latency, lambda_received_at),
                    ('NotificationLatencySeconds', notification_latency, slack_accepted_at),
                ],
                metric_pipeline,
                event_id,
                event_name,
                timestamp,
            )
