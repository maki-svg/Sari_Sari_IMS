from django.core.management.base import BaseCommand
from django.utils import timezone
from dashboard.models import Borrower

class Command(BaseCommand):
    help = 'Update borrower statuses based on due dates'

    def handle(self, *args, **options):
        today = timezone.now().date()
        
        # Update overdue borrowers
        updated = Borrower.objects.filter(
            status='active',
            due_date__lte=today  # Changed to lte for same day
        ).exclude(
            status='paid'
        ).update(status='overdue')
        
        self.stdout.write(
            self.style.SUCCESS(f'Updated {updated} borrowers to overdue status')
        )