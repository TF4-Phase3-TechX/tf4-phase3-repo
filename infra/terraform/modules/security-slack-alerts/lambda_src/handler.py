import json
import os
import urllib.request
import logging
import boto3
from datetime import datetime, timezone
import re

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm_client = boto3.client('ssm')
WEBHOOK_URL = None

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
        WEBHOOK_URL = response['Parameter']['Value']
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

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    
    for record in event.get('Records', []):
        sns_message = record.get('Sns', {}).get('Message')
        if not sns_message:
            continue
            
        try:
            message = json.loads(sns_message)
        except json.JSONDecodeError:
            logger.error("SNS Message is not valid JSON")
            continue
            
        source = message.get('source')
        detail = message.get('detail', {})
        
        event_name = "UnknownEvent"
        actor = "UnknownActor"
        account = message.get('account', 'UnknownAccount')
        region = message.get('region', 'UnknownRegion')
        timestamp = message.get('time', 'UnknownTime')
        source_ip = "UnknownIP"
        severity = "high"
        
        should_alert = True
        
        if source == 'aws.cloudtrail':
            event_name = detail.get('eventName', 'UnknownEvent')
            user_identity = detail.get('userIdentity', {})
            actor = user_identity.get('arn') or user_identity.get('principalId', 'UnknownActor')
            source_ip = detail.get('sourceIPAddress', 'UnknownIP')
            
            # Allowlist check to reduce noise
            if actor and re.search(r'role/tf4-github-actions', actor):
                should_alert = False
                logger.info(f"Ignoring event {event_name} by allowlisted actor {actor}")
                
            # Allowlist for EKS nodes or similar known services could go here

            
            # Filter logic
            if event_name == 'AuthorizeSecurityGroupIngress':
                if not is_public_sg_ingress(detail.get('requestParameters')):
                    should_alert = False
                    logger.info("Ignoring AuthorizeSecurityGroupIngress as it is not public (0.0.0.0/0 or ::/0).")
            elif event_name in ['PutBucketPolicy', 'PutBucketAcl']:
                # Very basic check, should ideally parse fully
                request_params = detail.get('requestParameters', {})
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
                         
            if event_name in ['StopLogging', 'DeleteTrail', 'DeleteConfigurationRecorder']:
                severity = "critical"
                
        elif source == 'aws.access-analyzer':
            event_name = "AccessAnalyzerFinding"
            actor = "AccessAnalyzer"
            severity = "critical"
            # Extract finding details if needed
            finding_id = detail.get('id', 'UnknownID')
            event_name = f"AccessAnalyzer Finding: {finding_id}"
            
        else:
             logger.warning(f"Unknown source: {source}")
             
        if not should_alert:
            continue
            
        short_actor = actor
        if actor and '/' in actor:
            short_actor = actor.split('/')[-1]

        latency_msg = "Unknown"
        display_time = timestamp
        if timestamp != 'UnknownTime':
            try:
                event_dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                now_dt = datetime.now(timezone.utc)
                delta_sec = (now_dt - event_dt).total_seconds()
                latency_msg = f"{delta_sec:.2f} giây"
                logger.info(f"Metric: Mandate11/DetectionLatency = {delta_sec}")
                
                from datetime import timedelta
                event_dt_vn = event_dt + timedelta(hours=7)
                display_time = f"{event_dt_vn.strftime('%Y-%m-%d %H:%M:%S')} +07 (UTC: {timestamp})"
            except Exception as e:
                logger.warning(f"Could not parse timestamp {timestamp}: {e}")

        cloudtrail_link = f"https://{region}.console.aws.amazon.com/cloudtrail/home?region={region}#/events?EventName={event_name}"
        if source != 'aws.cloudtrail':
            cloudtrail_link = "N/A"
            
        runbook_link = "https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/evidence/mandate-011-catch-at-real-time/test-runbook.md"
            
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
                                    "text": f"*Latency:*\n`{latency_msg}`"
                                }
                            ]
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Source IP:* `{source_ip}`\n*Noise check:* ❌ Không khớp allowlist CI/CD → cảnh báo thật\n*Investigate:* <{cloudtrail_link}|View in CloudTrail> | *Runbook:* <{runbook_link}|Security Runbook>"
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
        
        try:
            response = urllib.request.urlopen(req)
            logger.info(f"Message sent to Slack. Response status: {response.status}")
        except urllib.error.HTTPError as e:
            logger.error(f"Failed to send message to Slack. HTTP Error: {e.code} - {e.read().decode('utf-8')}")
        except urllib.error.URLError as e:
            logger.error(f"Failed to send message to Slack. URL Error: {e.reason}")
