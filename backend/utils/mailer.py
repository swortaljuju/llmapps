import os.path
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from utils.logger import logger

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
APP_MANAGER_GMAIL_CREDS_PATH = os.getenv('APP_MANAGER_GMAIL_CREDS_PATH', 'creds.json')
def gmail_login():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                APP_MANAGER_GMAIL_CREDS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds

def send_email(receiver_email: str, subject: str, content: str):
    try:
        creds = gmail_login()
        service = build('gmail', 'v1', credentials=creds)

        message = EmailMessage()
        message.set_content(content)
        message['To'] = receiver_email
        message['From'] =  os.getenv('APP_MANAGER_EMAIL','')  # Sender's email address
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        service.users().messages().send(userId="me", body=create_message).execute()
    except HttpError as error:
        logger.error(f"Failed to send email. subject {subject}; error: {error}")

