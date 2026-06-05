import json
import os
import boto3
import logging

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns = boto3.client('sns', region_name='us-east-1')
TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')

def lambda_handler(event, context):
    """
    Triggered by SQS batches.
    Processes appointment events and publishes them to SNS.
    Raises exceptions on failure to ensure SQS retry/DLQ mechanics work.
    """
    for record in event['Records']:
        try:
            body = json.loads(record['body'])
            appointment_id = body.get('appointment_id')
            user_id = body.get('user_id')
            status = body.get('status')
            
            message = f"Update for Appointment {appointment_id}: Status changed to {status}"
            
            sns.publish(
                TopicArn=TOPIC_ARN,
                Subject="MediLink Appointment Update",
                Message=message
            )
            
            logger.info("Notification sent", extra={
                "appointment_id": appointment_id,
                "user_id": user_id,
                "status": status,
                "message_id": record['messageId']
            })
            
        except Exception as e:
            logger.error(f"Failed to process record: {e}", extra={
                "record_body": record.get('body'),
                "message_id": record.get('messageId')
            })
            # Raising the exception tells SQS this specific message failed in the batch.
            # Lambda + SQS integration will automatically retry it until maxReceiveCount.
            raise e

    return {"statusCode": 200, "body": "Success"}
