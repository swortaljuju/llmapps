import smtplib, ssl
import os

ACCOUNT_MANAGER_EMAIL = os.getenv('APP_MANAGER_EMAIL','')
ACCOUNT_MANAGER_PASSWORD = os.getenv('APP_MANAGER_PASSWORD','')
PORT = 465  # For SSL
SMTP_SERVER = "smtp.gmail.com"

def send_email( receiver_email: str, subject: str, content: str):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, PORT, context=context) as server:
        server.login(ACCOUNT_MANAGER_EMAIL, ACCOUNT_MANAGER_PASSWORD)
        message = f"""\
            subject: {subject}
        
            {content}"""
        server.sendmail(ACCOUNT_MANAGER_EMAIL, receiver_email, message)
