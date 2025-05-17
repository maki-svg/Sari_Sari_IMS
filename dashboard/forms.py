from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.utils import timezone
from decimal import Decimal
from .models import Product, Sale, Borrower, BorrowedItem
import os
from datetime import timedelta, datetime
from django.db.models import Q
from django.db import models
import logging
from django.core.validators import validate_email

logger = logging.getLogger(__name__)

# Product Categories
CATEGORY = (
    ('Electronics', 'Electronics'),
    ('Snacks', 'Snacks'),
    ('Beverages', 'Beverages'),
    ('Household', 'Household'),
    ('Stationary', 'Stationary'),
)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'category', 'price', 'stock']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter product name'
            }),
            'category': forms.Select(
                attrs={'class': 'form-control'},
                choices=Product.CATEGORY
            ),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter price'
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter stock quantity'
            })
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise ValidationError('Product name is required.')
            
        # Check for existing product with same name for current user only
        if self.instance.pk:  # If updating
            if Product.objects.filter(
                user=self.user,
                name__iexact=name
            ).exclude(id=self.instance.pk).exists():
                raise ValidationError('You already have a product with this name.')
        else:  # If creating new
            if Product.objects.filter(user=self.user, name__iexact=name).exists():
                raise ValidationError('You already have a product with this name.')
        
        return name.title()  # Return the name in title case

class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['product', 'quantity', 'buyer_name']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # For editing, include the current product
        if self.instance.pk:
            self.fields['product'].queryset = Product.objects.filter(
                Q(stock__gt=0) | Q(pk=self.instance.product.pk)
            )
            # Make product field readonly for editing
            self.fields['product'].widget.attrs['readonly'] = True
            self.fields['product'].widget.attrs['disabled'] = True
        else:
            self.fields['product'].queryset = Product.objects.filter(stock__gt=0)

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')
        
        if not product or not quantity:
            return cleaned_data

        # For editing, consider the original quantity
        if self.instance.pk:
            original_quantity = self.instance.quantity
            available_stock = product.stock + original_quantity
            
            if quantity < 1:
                raise ValidationError({
                    'quantity': 'Quantity must be at least 1'
                })
            
            if quantity > available_stock:
                raise ValidationError({
                    'quantity': f'Not enough stock. Only {available_stock} units available.'
                })
        else:  # Only for new sales
            cleaned_data['date'] = timezone.now()
        
        return cleaned_data

class BorrowerForm(forms.ModelForm):
    class Meta:
        model = Borrower
        fields = [
            'borrower_name', 
            'contact_number', 
            'email',
            'address', 
            'signature', 
            'date_borrowed', 
            'due_date',
            'notes'
        ]
        widgets = {
            'borrower_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter borrower name'
            }),
            'contact_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter address'
            }),
            'date_borrowed': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes (optional)'
            })
        }

    def clean(self):
        logger.info("Starting BorrowerForm validation")
        cleaned_data = super().clean()
        logger.debug(f"Initial cleaned data: {cleaned_data}")
        
        # Validate borrower name
        borrower_name = cleaned_data.get('borrower_name')
        if borrower_name:
            logger.debug(f"Validating borrower name: {borrower_name}")
            cleaned_data['borrower_name'] = borrower_name.strip().title()
            
        # Validate dates
        date_borrowed = cleaned_data.get('date_borrowed')
        due_date = cleaned_data.get('due_date')
        
        if date_borrowed and due_date:
            logger.debug(f"Validating dates - borrowed: {date_borrowed}, due: {due_date}")
            if due_date < date_borrowed:
                logger.warning("Invalid dates: due date is before borrow date")
                raise ValidationError("Due date cannot be before borrow date")
        
        # Validate contact number
        contact_number = cleaned_data.get('contact_number')
        if contact_number:
            logger.debug(f"Validating contact number: {contact_number}")
            # The model's validator will handle the actual validation
            
        # Validate email if provided
        email = cleaned_data.get('email')
        if email:
            logger.debug(f"Validating email: {email}")
            try:
                validate_email(email)
            except ValidationError as e:
                logger.warning(f"Invalid email: {str(e)}")
                self.add_error('email', str(e))
        
        # Log any form errors
        if self.errors:
            logger.warning(f"Form validation errors: {self.errors}")
        else:
            logger.info("Form validation successful")
        
        return cleaned_data

class BorrowedItemForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True, stock__gt=0),
        empty_label="Select a product",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'required': True
        })
    )
    
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter quantity',
            'required': True
        })
    )

    class Meta:
        model = BorrowedItem
        fields = ['product', 'quantity']