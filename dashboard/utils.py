from django.conf import settings
from twilio.rest import Client
from django.utils import timezone
from django.core.mail import send_mail
import logging
import requests

logger = logging.getLogger(__name__)

# dashboard/utils.py
def format_phone_number(phone_number):
    """Format phone number to E.164 format"""
    # Remove any non-digit characters
    cleaned = ''.join(filter(str.isdigit, phone_number))
    
    # Add Philippines country code if not present
    if len(cleaned) == 10 and cleaned.startswith('9'):
        return f'+63{cleaned}'
    elif len(cleaned) == 11 and cleaned.startswith('0'):
        return f'+63{cleaned[1:]}'
    elif len(cleaned) == 12 and cleaned.startswith('63'):
        return f'+{cleaned}'
    return f'+{cleaned}' if not cleaned.startswith('+') else cleaned

def verify_phone_number(phone_number):
    """Verify phone number before sending SMS"""
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        verification = client.verify \
            .v2 \
            .services(settings.TWILIO_VERIFY_SERVICE_SID) \
            .verifications \
            .create(to=phone_number, channel='sms')
        return True
    except Exception as e:
        logger.error(f"Failed to verify phone number: {str(e)}")
        return False

def send_sms(to_number, message):
    """Send SMS with proper error handling"""
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # Format the phone number
        formatted_number = format_phone_number(to_number)
        
        # Log attempt
        logger.info(f"Attempting to send SMS to {formatted_number}")
        
        # First verify the number
        if not verify_phone_number(formatted_number):
            logger.error(f"Phone number verification failed: {formatted_number}")
            return False
            
        # Send message
        message = client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=formatted_number
        )
        
        logger.info(f"SMS sent successfully. SID: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send SMS: {str(e)}")
        return False

def send_notification_email(borrower, message):
    """Send email notification"""
    try:
        subject = 'Sari-Sari Store Loan Notification'
        from_email = settings.EMAIL_HOST_USER
        recipient_list = [borrower.email]  # Add email field to Borrower model
        
        send_mail(
            subject,
            message,
            from_email,
            recipient_list,
            fail_silently=False,
        )
        logger.info(f"Email sent to {borrower.borrower_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False

def send_telegram_message(chat_id, message):
    """Send message via Telegram bot"""
    try:
        bot_token = settings.TELEGRAM_BOT_TOKEN
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        logger.info(f"Telegram message sent to {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {str(e)}")
        return False

def send_overdue_notification(borrower):
    """Send overdue notification via email, SMS, and Telegram"""
    email_message = (
        f"Dear {borrower.borrower_name},\n\n"
        f"Your loan payment of ₱{borrower.total_debt} was due on "
        f"{borrower.due_date}. Please settle your payment as soon as possible.\n\n"
        f"Thank you,\nSari-Sari Store"
    )
    sms_message = (
        f"Dear {borrower.borrower_name}, your loan payment of ₱{borrower.total_debt} was due on "
        f"{borrower.due_date}. Please settle your payment as soon as possible."
    )
    telegram_message = (
        f"<b>OVERDUE NOTICE</b>\n\n"
        f"Dear {borrower.borrower_name},\n"
        f"Your loan payment of ₱{borrower.total_debt} was due on "
        f"{borrower.due_date}. Please settle your payment as soon as possible."
    )
    email_sent = send_notification_email(borrower, email_message)
    sms_sent = send_sms(borrower.contact_number, sms_message)
    telegram_sent = send_telegram_message(borrower.telegram_chat_id, telegram_message)
    return email_sent and sms_sent and telegram_sent

def send_due_date_warning(borrower, days_remaining):
    """Send warning notification via email, SMS, and Telegram"""
    email_message = (
        f"Dear {borrower.borrower_name},\n\n"
        f"This is a reminder that your loan payment of ₱{borrower.total_debt} "
        f"is due in {days_remaining} days on {borrower.due_date}. "
        f"Please prepare for payment.\n\n"
        f"Thank you,\nSari-Sari Store"
    )
    sms_message = (
        f"Dear {borrower.borrower_name}, this is a reminder that your "
        f"loan payment of ₱{borrower.total_debt} is due in {days_remaining} "
        f"days on {borrower.due_date}. Please prepare for payment."
    )
    telegram_message = (
        f"<b>PAYMENT REMINDER</b>\n\n"
        f"Dear {borrower.borrower_name},\n"
        f"Your loan payment of ₱{borrower.total_debt} is due in {days_remaining} "
        f"days on {borrower.due_date}. Please prepare for payment."
    )
    email_sent = send_notification_email(borrower, email_message)
    sms_sent = send_sms(borrower.contact_number, sms_message)
    telegram_sent = send_telegram_message(borrower.telegram_chat_id, telegram_message)
    return email_sent and sms_sent and telegram_sent