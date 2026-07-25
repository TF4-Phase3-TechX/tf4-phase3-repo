import json
import os
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client('sqs')
lambda_client = boto3.client('lambda')

DLQ_URL = os.environ.get('DLQ_URL')
MAIN_LAMBDA_NAME = os.environ.get('MAIN_LAMBDA_NAME')

def lambda_handler(event, context):
    if not DLQ_URL or not MAIN_LAMBDA_NAME:
        logger.error("Missing DLQ_URL or MAIN_LAMBDA_NAME environment variable")
        return
        
    logger.info(f"Starting redrive process from DLQ: {DLQ_URL} to Lambda: {MAIN_LAMBDA_NAME}")
    
    total_processed = 0
    total_failed = 0
    
    while True:
        # Receive up to 10 messages
        response = sqs_client.receive_message(
            QueueUrl=DLQ_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=1 # Short wait to keep processing fast
        )
        
        messages = response.get('Messages', [])
        if not messages:
            logger.info("No more messages in DLQ to process.")
            break
            
        for msg in messages:
            receipt_handle = msg['ReceiptHandle']
            try:
                body = json.loads(msg['Body'])
                
                # The body from Lambda Destination on_failure is an envelope
                # containing requestPayload, responseContext, responsePayload, etc.
                request_payload = body.get('requestPayload')
                
                if not request_payload:
                    logger.warning(f"Message {msg['MessageId']} does not contain a requestPayload. Skipping.")
                    continue
                
                # Invoke the main lambda asynchronously
                # If we want to wait to ensure Slack is up, we could use RequestResponse,
                # but Event is safer to avoid redriver timeout.
                # Actually, RequestResponse is better here so we don't just dump everything 
                # back into the DLQ instantly if Slack is STILL down.
                # However, if we use RequestResponse, we could hit timeout.
                # Let's use Event (async). If Slack is still down, the main lambda will retry
                # and then fail, and it will end up back in the DLQ. 
                
                logger.info(f"Redriving message {msg['MessageId']} to main lambda.")
                
                lambda_client.invoke(
                    FunctionName=MAIN_LAMBDA_NAME,
                    InvocationType='Event',
                    Payload=json.dumps(request_payload)
                )
                
                # Delete from DLQ since we successfully handed it off to the main Lambda
                sqs_client.delete_message(
                    QueueUrl=DLQ_URL,
                    ReceiptHandle=receipt_handle
                )
                total_processed += 1
                
            except Exception as e:
                logger.error(f"Failed to process message {msg['MessageId']}: {str(e)}")
                total_failed += 1
                
        # Stop if we are about to hit the Lambda timeout (leave 10 seconds buffer)
        if context.get_remaining_time_in_millis() < 10000:
            logger.warning("Approaching Lambda timeout, stopping redrive loop.")
            break
            
    logger.info(f"Redrive complete. Successfully processed: {total_processed}, Failed: {total_failed}")
    
    return {
        'processedCount': total_processed,
        'failedCount': total_failed
    }
