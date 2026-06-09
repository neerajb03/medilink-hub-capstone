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
            
            if status == "pending":
                message = (
                    f"Hello,\n\n"
                    f"Your appointment (ID: {appointment_id}) has been successfully requested.\n"
                    f"It is currently pending approval from the doctor."
                )
                subject = "Appointment Requested - Pending Approval"
            elif status == "accepted":
                message = (
                    f"Great news!\n\n"
                    f"Your appointment (ID: {appointment_id}) has been officially accepted by the doctor.\n"
                    f"We look forward to seeing you."
                )
                subject = "Appointment Accepted!"
            elif status == "completed":
                message = (
                    f"Hello,\n\n"
                    f"Your appointment (ID: {appointment_id}) has been marked as completed.\n"
                    f"You can now securely view any associated health records and documents on the MediLink portal."
                )
                subject = "Appointment Completed - Records Available"
            elif status == "denied":
                message = (
                    f"Hello,\n\n"
                    f"Unfortunately, your appointment request (ID: {appointment_id}) could not be accepted at this time.\n"
                    f"Please try scheduling a different time slot through the portal."
                )
                subject = "Appointment Update - Request Denied"
            else:
                message = f"Update for Appointment {appointment_id}: Status changed to {status}"
                subject = "MediLink Appointment Update"
            
            sns.publish(
                TopicArn=TOPIC_ARN,
                Subject=subject,
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
