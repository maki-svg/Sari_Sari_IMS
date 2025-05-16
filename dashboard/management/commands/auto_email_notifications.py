from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from dashboard.models import Borrower
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Automatically send email notifications for due dates and overdue loans'

    def handle(self, *args, **options):
        today = timezone.now().date()
        notifications_sent = 0

        # Get overdue borrowers
        overdue_borrowers = Borrower.objects.filter(
            status='active',
            due_date__lt=today,
            email__isnull=False
        ).exclude(email='')

        # Get borrowers with upcoming due dates (3 days warning)
        upcoming_due = Borrower.objects.filter(
            status='active',
            due_date=today + timedelta(days=3),
            email__isnull=False
        ).exclude(email='')

        # Send overdue notifications
        for borrower in overdue_borrowers:
            try:
                subject = "OVERDUE PAYMENT NOTICE - Sari-Sari Store"
                message = (
                    f"Dear {borrower.borrower_name},\n\n"
                    f"Your loan payment of ₱{borrower.total_debt:,.2f} "
                    f"was due on {borrower.due_date}.\n\n"
                    f"Please settle your payment as soon as possible.\n\n"
                    f"Best regards,\nSari-Sari Store"
                )
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[borrower.email],
                    fail_silently=False,
                )
                
                notifications_sent += 1
                if borrower.status != 'overdue':
                    borrower.status = 'overdue'
                    borrower.save(update_fields=['status'])
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent overdue notification to {borrower.borrower_name}"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to send notification to {borrower.borrower_name}: {str(e)}"
                    )
                )

        # Send upcoming due date notifications
        for borrower in upcoming_due:
            try:
                subject = "Payment Due Soon - Sari-Sari Store"
                message = (
                    f"Dear {borrower.borrower_name},\n\n"
                    f"This is a reminder that your loan payment of ₱{borrower.total_debt:,.2f} "
                    f"is due in 3 days on {borrower.due_date}.\n\n"
                    f"Please prepare for the payment.\n\n"
                    f"Best regards,\nSari-Sari Store"
                )
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[borrower.email],
                    fail_silently=False,
                )
                
                notifications_sent += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent due date reminder to {borrower.borrower_name}"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to send reminder to {borrower.borrower_name}: {str(e)}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f"Successfully sent {notifications_sent} notifications")
        )