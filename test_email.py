import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load environment variables
load_dotenv()

# Email settings
email_host = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
email_port = int(os.getenv('EMAIL_PORT', '587'))
email_host_user = os.getenv('EMAIL_HOST_USER', '')
email_host_password = os.getenv('EMAIL_HOST_PASSWORD', '')

print(f"Email Host: {email_host}")
print(f"Email Port: {email_port}")
print(f"Email User: {email_host_user}")
print(f"Password length: {len(email_host_password)}")

try:
    # Create message
    msg = MIMEMultipart()
    msg['From'] = email_host_user
    msg['To'] = email_host_user
    msg['Subject'] = "Test Email from SariSync"
    body = "This is a test email to verify the configuration."
    msg.attach(MIMEText(body, 'plain'))

    # Create server connection
    server = smtplib.SMTP(email_host, email_port)
    server.starttls()
    
    # Login
    print("Attempting to login...")
    server.login(email_host_user, email_host_password)
    print("Login successful!")
    
    # Send email
    text = msg.as_string()
    server.sendmail(email_host_user, email_host_user, text)
    print("Email sent successfully!")
    
    # Close connection
    server.quit()
    
except Exception as e:
    print(f"Error: {str(e)}") 