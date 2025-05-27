# send_email.py

from typing import List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from config import settings

def send_email(subject: str, html_content: str, recipients: List[str]):
    for email in recipients:
        try:
            msg = MIMEMultipart()
            msg["From"] = settings.EMAIL_ADDRESS
            msg["To"] = email
            msg["Subject"] = subject

            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
                server.send_message(msg)

            print(f"Email sent to {email}")
        except Exception as e:
            print(f"Failed to send email to {email}: {e}")
            raise Exception(f"Failed to send email to {email}")
