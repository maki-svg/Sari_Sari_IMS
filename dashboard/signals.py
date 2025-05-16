from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Borrower
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Borrower)
def update_borrower_status(sender, instance, created, **kwargs):
    """Update borrower status when saved"""
    try:
        if not created and instance.status != 'paid':
            today = timezone.now().date()
            if instance.due_date and instance.due_date <= today:
                if not kwargs.get('skip_status_update', False):
                    instance.status = 'overdue'
                    instance.save(skip_status_update=True, update_fields=['status'])
    except Exception as e:
        logger.error(f"Error updating borrower status: {str(e)}")
