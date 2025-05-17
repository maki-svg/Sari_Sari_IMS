from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import F, Sum
from django.db import transaction
from django.core.validators import MinValueValidator, RegexValidator
from decimal import Decimal
from datetime import datetime, date
from django.contrib.auth.models import User
from django.urls import reverse
from django.db.models import Count
from .utils import send_overdue_notification
from django.core.mail import send_mail
from django.conf import settings
import logging
from django.core.validators import validate_email
from cloudinary.models import CloudinaryField

logger = logging.getLogger(__name__)
class Product(models.Model):
    # Update CATEGORY choices to be a tuple for immutability
    CATEGORY = (
        ('Electronics', 'Electronics'),
        ('Snacks', 'Snacks'),
        ('Beverages', 'Beverages'),
        ('Household', 'Household'),
        ('Stationary', 'Stationary'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=100)  # Remove unique=True since it should be unique per user
    category = models.CharField(
        max_length=100, 
        choices=CATEGORY,
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    stock = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)  # Add this field for soft deletion
    deleted_at = models.DateTimeField(null=True, blank=True)  # Add this field to track deletion time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Products'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['category']),
            models.Index(fields=['stock']),
            models.Index(fields=['price']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_deleted']),
            models.Index(fields=['user']),  # Add index for user
        ]
        constraints = [
            models.UniqueConstraint(  # Add unique constraint for name per user
                fields=['user', 'name'],
                name='unique_product_name_per_user'
            )
        ]

    @property
    def is_low_stock(self):
        return 0 < self.stock <= 5
        
    @property
    def stock_value(self):
        return self.stock * self.price

    def __str__(self):
        return f'{self.name} - {self.category} - ₱{self.price:.2f} - Stock: {self.stock}'

    def clean(self):
        # Convert name to title case for consistency
        self.name = self.name.title()
        if self.price <= 0:
            raise ValidationError("Price must be greater than zero")
        if self.stock < 0:
            raise ValidationError("Stock cannot be negative")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def soft_delete(self):
        """Soft delete the product instead of actually deleting it"""
        self.is_deleted = True
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save()

class Sale(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sales')  # Make user required
    product = models.ForeignKey(
        'Product',
        on_delete=models.PROTECT,
        related_name='sales'
    )
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    buyer_name = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    date = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_recorded'
    )

    class Meta:
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['user']),
            models.Index(fields=['product']),
        ]

    def save(self, *args, **kwargs):
        """Handle stock updates and timezone awareness"""
        if not self.date:
            self.date = timezone.now()
        elif timezone.is_naive(self.date):
            self.date = timezone.make_aware(self.date)

        if not self.pk:  # New sale
            with transaction.atomic():
                # Ensure product belongs to the same user
                if self.product.user != self.user:
                    raise ValidationError("You can only sell your own products.")
                    
                product = Product.objects.select_for_update().get(pk=self.product.pk)
                if product.stock < self.quantity:
                    raise ValidationError(f"Not enough stock. Only {product.stock} available.")
                product.stock -= self.quantity
                product.save()
                if not self.price:
                    self.price = product.price
        else:  # Existing sale
            if not self.price:
                self.price = self.product.price
                
        super().save(*args, **kwargs)

    @property
    def total(self):
        return self.price * self.quantity

    @classmethod
    def get_sales_summary(cls):
        """Get aggregated sales data"""
        return cls.objects.aggregate(
            total_sales=Sum(F('price') * F('quantity')),
            total_transactions=Count('id'),
            total_items=Sum('quantity')
        )

class Borrower(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='borrowers', null=True)  # Make nullable initially
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]

    borrower_name = models.CharField(
        max_length=100,
        error_messages={
            'unique': "A borrower with this name already exists."
        }
    )  # Remove unique=True since it should be unique per user
    contact_number = models.CharField(max_length=20, validators=[
        RegexValidator(
            regex=r'^(\+63|0)?(9\d{9})$',
            message="Phone number must be a valid Philippine mobile number (e.g., 09123456789 or +639123456789)"
        )
    ])
    address = models.TextField()
    signature = CloudinaryField(
        'signature',
        folder='signatures',
        null=True,
        blank=True,
        help_text="Upload borrower's signature (optional)"
    )
    email = models.EmailField(
        max_length=254, 
        blank=True, 
        null=True,
        help_text="Email address for notifications",
        error_messages={
            'invalid': "Please enter a valid email address."
        }
    )
    telegram_chat_id = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Telegram chat ID for notifications"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    date_borrowed = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-date_borrowed']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['borrower_name']),
            models.Index(fields=['email']),
            models.Index(fields=['user']),  # Add index for user
        ]
        constraints = [
            models.UniqueConstraint(  # Update unique constraint for borrower name per user
                fields=['user', 'borrower_name'],
                name='unique_borrower_name_per_user'
            )
        ]

    @property
    def total_debt(self):
        return sum(item.total for item in self.items.all())

    @property
    def items_count(self):
        return self.items.count()

    @property
    def returned_items_count(self):
        return self.items.filter(is_returned=True).count()

    @property
    def payment_status(self):
        if self.items_count == 0:
            return 'no_items'
        if self.returned_items_count == self.items_count:
            return 'paid'
        return 'pending'

    @property
    def current_status(self):
        """Calculate real-time status without recursion"""
        if self.status == 'paid':
            return 'paid'
        
        today = timezone.now().date()
        if self.due_date and self.due_date <= today:
            return 'overdue'
        return 'active'

    def clean(self):
        today = timezone.now().date()
        
        if self.date_borrowed:
            if isinstance(self.date_borrowed, datetime):
                date_borrowed = self.date_borrowed.date()
            else:
                date_borrowed = self.date_borrowed
                
            if date_borrowed > today:
                raise ValidationError("Borrow date cannot be in the future")
        
        if self.due_date:
            if isinstance(self.due_date, datetime):
                due_date = self.due_date.date()
            else:
                due_date = self.due_date
                
            if due_date < self.date_borrowed:
                raise ValidationError("Due date cannot be before borrow date")
            
        # Validate email if provided
        if self.email:
            self.email = self.email.strip()  # Remove any whitespace
            if not self.email:  # If email is just whitespace
                self.email = None
            else:
                try:
                    validate_email(self.email)
                except ValidationError:
                    raise ValidationError({'email': 'Please enter a valid email address'})

    def save(self, *args, **kwargs):
        # Clean up old signature if a new one is being set
        if self.pk:
            try:
                old_instance = Borrower.objects.get(pk=self.pk)
                if old_instance.signature and self.signature != old_instance.signature:
                    old_instance.signature.delete(save=False)
            except Borrower.DoesNotExist:
                pass

        # Clean and validate email before saving
        if self.email:
            self.email = self.email.strip()
            if not self.email:
                self.email = None

        super().save(*args, **kwargs)

    def check_and_notify_if_overdue(self):
        today = timezone.now().date()
        if (self.status == 'active' and 
            self.due_date and 
            self.due_date < today):
            
            from .utils import send_overdue_notification  # Add this import
            if send_overdue_notification(self):
                self.status = 'overdue'
                self.save()
                return True
        return False

    def send_email_notification(self, subject, message):
        """Send email notification to borrower"""
        if self.email:
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[self.email],
                    fail_silently=False,
                )
                return True
            except Exception as e:
                logger.error(f"Failed to send email to {self.email}: {str(e)}")
                return False
        return False

    def send_overdue_notification(self):
        """Send overdue notification"""
        subject = "OVERDUE PAYMENT NOTICE - Sari-Sari Store"
        message = (
            f"Dear {self.borrower_name},\n\n"
            f"This is to inform you that your loan payment of ₱{self.total_debt:,.2f} "
            f"was due on {self.due_date}.\n\n"
            f"Please settle your payment as soon as possible.\n\n"
            f"Best regards,\nSari-Sari Store"
        )
        return self.send_email_notification(subject, message)

    def send_due_date_reminder(self, days_remaining):
        """Send due date reminder"""
        subject = f"Payment Due in {days_remaining} days - Sari-Sari Store"
        message = (
            f"Dear {self.borrower_name},\n\n"
            f"This is a reminder that your loan payment of ₱{self.total_debt:,.2f} "
            f"is due in {days_remaining} days on {self.due_date}.\n\n"
            f"Please prepare for the payment.\n\n"
            f"Best regards,\nSari-Sari Store"
        )
        return self.send_email_notification(subject, message)

    def __str__(self):
        return self.borrower_name

class BorrowedItem(models.Model):
    borrower = models.ForeignKey(Borrower, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    date_borrowed = models.DateField(default=timezone.now)
    is_returned = models.BooleanField(default=False)

    @property
    def total(self):
        return self.price * self.quantity

class InventoryAudit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audits', null=True)  # Make nullable initially
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='audits')
    system_count = models.PositiveIntegerField()  # Stock count in system
    physical_count = models.PositiveIntegerField()  # Actual physical count
    discrepancy = models.IntegerField()  # Can be positive or negative
    notes = models.TextField(blank=True, null=True)
    conducted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='conducted_audits')
    audit_date = models.DateTimeField(auto_now_add=True)
    adjusted = models.BooleanField(default=False)  # Whether discrepancy was resolved

    class Meta:
        ordering = ['-audit_date']
        indexes = [
            models.Index(fields=['audit_date']),
            models.Index(fields=['adjusted']),
            models.Index(fields=['user']),  # Add index for user field
        ]

    def save(self, *args, **kwargs):
        # Calculate discrepancy
        self.discrepancy = self.physical_count - self.system_count
        super().save(*args, **kwargs)

    def adjust_inventory(self):
        """Adjust inventory to match physical count"""
        if not self.adjusted:
            with transaction.atomic():
                self.product.stock = self.physical_count
                self.product.save()
                self.adjusted = True
                self.save()