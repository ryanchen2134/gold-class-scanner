
import smtplib

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import email_addr as from_email, email_password as password


def send_email(subject, body, to_email):

    smtp_server = 'smtp.gmail.com'
    smtp_port = 587  #TLS


    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
       
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.ehlo()
        server.starttls()
        server.ehlo()

        server.login(from_email, password)

        server.send_message(msg)
        print(f"Email sent successfully to {to_email}")

    except Exception as e:
        print(f"An error occurred while sending the email: {e}")

    finally:
        server.quit()

