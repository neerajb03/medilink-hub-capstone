import json
import os
import boto3
import logging

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

ses = boto3.client('ses', region_name='us-east-1')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')

def lambda_handler(event, context):
    """
    Triggered by SQS batches.
    Processes appointment events and sends emails via SES.
    """
    if not ADMIN_EMAIL:
        logger.error("ADMIN_EMAIL environment variable not set")
        return {"statusCode": 500, "body": "Configuration error"}

    for record in event['Records']:
        try:
            body = json.loads(record['body'])
            appointment_id = body.get('appointment_id')
            patient_name = body.get('patient_name', 'Patient')
            patient_email = body.get('patient_email', 'unknown')
            doctor_name = body.get('doctor_name', 'Doctor')
            status = body.get('status')
            
            audit_header = f"""
            <div style="background-color: #ffe0b2; padding: 10px; border-left: 4px solid #ff9800; margin-bottom: 20px; font-family: Arial, sans-serif;">
                <strong>[AUDIT LOG]</strong> This email would normally be delivered to: <strong>{patient_email}</strong><br>
                <em>AWS SES Sandbox mode is active, routing to admin instead.</em>
            </div>
            """
            
            if status == "pending":
                message = (
                    f"Dear {patient_name},<br><br>"
                    f"Your appointment request with Dr. {doctor_name} has been successfully received.<br>"
                    f"It is currently <strong>pending approval</strong> from the doctor.<br><br>"
                    f"Appointment ID: {appointment_id}"
                )
                subject = "Appointment Requested - Pending Approval"
            elif status == "accepted":
                message = (
                    f"Great news, {patient_name}!<br><br>"
                    f"Your appointment with Dr. {doctor_name} has been <strong>officially accepted</strong>.<br>"
                    f"We look forward to seeing you.<br><br>"
                    f"Appointment ID: {appointment_id}"
                )
                subject = "Appointment Accepted!"
            elif status == "completed":
                message = (
                    f"Hello {patient_name},<br><br>"
                    f"Your appointment with Dr. {doctor_name} has been marked as <strong>completed</strong>.<br>"
                    f"You can now securely view any associated health records and documents on the MediLink portal.<br><br>"
                    f"Appointment ID: {appointment_id}"
                )
                subject = "Appointment Completed - Records Available"
            elif status == "denied":
                message = (
                    f"Hello {patient_name},<br><br>"
                    f"Unfortunately, your appointment request with Dr. {doctor_name} could not be accepted at this time.<br>"
                    f"Please try scheduling a different time slot through the portal.<br><br>"
                    f"Appointment ID: {appointment_id}"
                )
                subject = "Appointment Update - Request Denied"
            else:
                message = f"Update for Appointment {appointment_id}: Status changed to {status}"
                subject = "MediLink Appointment Update"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                {audit_header}
                <div style="padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                    {message}
                </div>
                <div style="margin-top: 20px; font-size: 12px; color: #888;">
                    &copy; 2026 MediLink Hub. All rights reserved.
                </div>
            </body>
            </html>
            """
            
            ses.send_email(
                Source=ADMIN_EMAIL,
                Destination={
                    'ToAddresses': [ADMIN_EMAIL]
                },
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {'Html': {'Data': html_body, 'Charset': 'UTF-8'}}
                }
            )
            
            logger.info("Notification sent", extra={
                "appointment_id": appointment_id,
                "patient_name": patient_name,
                "status": status,
                "message_id": record['messageId']
            })
            
        except Exception as e:
            logger.error(f"Failed to process record: {e}", extra={
                "record_body": record.get('body'),
                "message_id": record.get('messageId')
            })
            raise e

    return {"statusCode": 200, "body": "Success"}
