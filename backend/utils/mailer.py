import os
from utils.logger import logger
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(receiver_email: str, subject: str, content: str):
    gmail_user = os.getenv('APP_MANAGER_EMAIL','') 
    app_password = os.getenv('APP_MANAGER_GMAIL_APP_PASSWORD', '')

    # Create message
    msg = MIMEMultipart()
    msg['From'] = gmail_user
    msg['To'] = receiver_email
    msg['Subject'] = subject

    # Email body
    msg.attach(MIMEText(content, 'html'))

    try:
        # Connect to Gmail SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Secure the connection
        server.login(gmail_user, app_password)
        server.sendmail(gmail_user, receiver_email, msg.as_string())
    except Exception as e:
        logger.error(f"Failed to send email. subject {subject}; error: {e}")
        raise e
    finally:
        server.quit()


