from django.contrib import admin
from django.contrib.auth.models import Group
from django.db import models, transaction
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError
from .models import Product, Sale, Borrower, BorrowedItem
from django.db.models import F, ExpressionWrapper, DecimalField
import logging
from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic.edit import CreateView

logger = logging.getLogger(__name__)

# Add error handling for stock updates in Sale model
def save(self, *args, **kwargs):
    try:
        with transaction.atomic():
            if not self.pk:  # New sale
                if self.product.stock < self.quantity:
                    raise ValidationError("Insufficient stock")
                self.product.stock -= self.quantity
                self.product.save()
            super().save(*args, **kwargs)
    except Exception as e:
        logger.error(f"Error saving sale: {str(e)}")
        raise

# Customizing the admin site header
admin.site.site_header = "Sari Sari Inventory Management System"
admin.site.site_title = "Inventory Admin Portal"
admin.site.index_title = "Welcome to Sari Sari Store Admin"

# Product Admin customization
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price_display', 'stock', 'stock_status', 'created_at', 'updated_at')
    list_filter = ('category', 'created_at')
    search_fields = ('name', 'category')
    list_editable = ('stock',)
    list_per_page = 20
    actions = ['restock_items', 'clear_stock']
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'category', 'price', 'stock')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def price_display(self, obj):
        return f"₱{obj.price:.2f}"
    price_display.short_description = 'Price'

    def stock_status(self, obj):
        if obj.stock <= 0:
            return format_html('<span style="color: red;">Out of Stock</span>')
        elif obj.stock < 10:
            return format_html('<span style="color: orange;">Low Stock ({})</span>', obj.stock)
        return format_html('<span style="color: green;">In Stock ({})</span>', obj.stock)
    stock_status.short_description = 'Stock Status'
    stock_status.admin_order_field = 'stock'

    def restock_items(self, request, queryset):
        updated = queryset.update(stock=models.F('stock') + 10)
        self.message_user(request, f"Successfully restocked {updated} products (+10 units each)")
    restock_items.short_description = "Restock selected items (+10 units)"

    def clear_stock(self, request, queryset):
        updated = queryset.update(stock=0)
        self.message_user(request, f"Cleared stock for {updated} products")
    clear_stock.short_description = "Clear stock (set to 0)"

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_date',
        'product',
        'formatted_quantity',
        'formatted_price',
        'formatted_total',
        'buyer_name_or_anonymous',
        'get_recorded_by'
    )
    list_select_related = ('product', 'recorded_by')
    list_filter = (
        ('date', admin.DateFieldListFilter),
        'product',
        ('recorded_by', admin.RelatedOnlyFieldListFilter),
    )
    readonly_fields = (
        'formatted_total',
        'date',
        'get_recorded_by'
    )
    fieldsets = (
        (None, {
            'fields': ('product', 'quantity', 'price')
        }),
        ('Customer Information', {
            'fields': ('buyer_name',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('date', 'recorded_by', 'formatted_total'),
            'classes': ('collapse',)
        })
    )

    # Custom admin methods
    def formatted_date(self, obj):
        return obj.date.strftime("%b %d, %Y %H:%M")
    formatted_date.short_description = 'Date/Time'
    formatted_date.admin_order_field = 'date'

    def formatted_quantity(self, obj):
        return f"{obj.quantity} units"
    formatted_quantity.short_description = 'Quantity'
    formatted_quantity.admin_order_field = 'quantity'

    def formatted_price(self, obj):
        return f"₱{obj.price:,.2f}"
    formatted_price.short_description = 'Unit Price'
    formatted_price.admin_order_field = 'price'

    def formatted_total(self, obj):
        return f"₱{obj.total:,.2f}"
    formatted_total.short_description = 'Total Amount'

    def buyer_name_or_anonymous(self, obj):
        return obj.buyer_name or "Anonymous"
    buyer_name_or_anonymous.short_description = 'Customer'

    def get_recorded_by(self, obj):
        return obj.recorded_by.get_full_name() if obj.recorded_by else '-'
    get_recorded_by.short_description = 'Recorded By'
    get_recorded_by.admin_order_field = 'recorded_by'

    def get_queryset(self, request):
        """Optimize queryset with annotations"""
        return super().get_queryset(request).annotate(
            calculated_total=ExpressionWrapper(
                F('price') * F('quantity'),
                output_field=DecimalField()
            )
        )

    def save_model(self, request, obj, form, change):
        """Set the recorded_by user on save"""
        if not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)

class BorrowedItemInline(admin.TabularInline):
    model = BorrowedItem
    extra = 1
    readonly_fields = ('price_display', 'date_borrowed', 'total_display', 'product_link')
    fields = ('product_link', 'quantity', 'price_display', 'date_borrowed', 'total_display')
    classes = ('collapse',)
    
    def product_link(self, obj):
        if obj.pk:
            # Update the URL pattern name to match your urls.py
            url = reverse("admin:dashboard_product_change", args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.product.name)
        return "-"
    product_link.short_description = 'Product'

    def price_display(self, obj):
        return f"₱{obj.price:.2f}" if obj.pk else "-"
    price_display.short_description = 'Price'

    def total_display(self, obj):
        return f"₱{obj.total:.2f}" if obj.pk else "-"
    total_display.short_description = 'Total'

@admin.register(Borrower)
class BorrowerAdmin(admin.ModelAdmin):
    list_display = (
        'borrower_name', 
        'contact_number', 
        'email',  # Add email to list display
        'status', 
        'date_borrowed', 
        'due_date', 
        'total_debt'
    )
    list_filter = ('status', 'date_borrowed', 'due_date')
    search_fields = ('borrower_name', 'contact_number', 'email')  # Add email to search
    readonly_fields = ('total_debt',)
    inlines = [BorrowedItemInline]
    
    def total_debt(self, obj):
        return f"₱{obj.total_debt:,.2f}"
    total_debt.short_description = 'Total Debt'

@admin.register(BorrowedItem)
class BorrowedItemAdmin(admin.ModelAdmin):
    list_display = ('borrower_link', 'product_link', 'quantity', 'price_display', 
                    'total_display', 'date_borrowed', 'status_filter')
    list_filter = ('date_borrowed', 'product__category', 'borrower__status')
    search_fields = ('borrower__borrower_name', 'product__name')
    readonly_fields = ('date_borrowed', 'total_display', 'borrower_link', 'product_link')
    list_select_related = ('borrower', 'product')
    list_per_page = 30

    def borrower_link(self, obj):
        # Update the URL pattern name
        url = reverse("admin:dashboard_borrower_change", args=[obj.borrower.id])
        return format_html('<a href="{}">{}</a>', url, obj.borrower.borrower_name)
    borrower_link.short_description = 'Borrower'
    borrower_link.admin_order_field = 'borrower__borrower_name'

    def product_link(self, obj):
        # Update the URL pattern name
        url = reverse("admin:dashboard_product_change", args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)
    product_link.short_description = 'Product'
    product_link.admin_order_field = 'product__name'

    def price_display(self, obj):
        return f"₱{obj.price:.2f}"
    price_display.short_description = 'Price'

    def total_display(self, obj):
        return f"₱{obj.total:.2f}"
    total_display.short_description = 'Total'

    def status_filter(self, obj):
        return obj.borrower.get_status_display()
    status_filter.short_description = 'Borrower Status'
    status_filter.admin_order_field = 'borrower__status'

# Add permission checks in views
class SaleCreateView(UserPassesTestMixin, CreateView):
    def test_func(self):
        return self.request.user.has_perm('dashboard.add_sale')

# Unregister Group if not needed
admin.site.unregister(Group)