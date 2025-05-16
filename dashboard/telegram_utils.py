import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

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
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {str(e)}")
        return False

def send_overdue_notification(borrower):
    """Send overdue notification via Telegram"""
    if not borrower.telegram_chat_id:
        return False
        
    message = (
        f"<b>OVERDUE NOTICE</b>\n\n"
        f"Dear {borrower.borrower_name},\n"
        f"Your loan payment of ₱{borrower.total_debt} was due on "
        f"{borrower.due_date}. Please settle your payment as soon as possible."
    )
    return send_telegram_message(borrower.telegram_chat_id, message)