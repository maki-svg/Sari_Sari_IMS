from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q, F, Prefetch, Count, Case, When, Value, BooleanField
from django.db.models.functions import Abs
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Product, Sale, Borrower, BorrowedItem, InventoryAudit
from .forms import ProductForm, SaleForm, BorrowerForm, BorrowedItemForm
from decimal import Decimal
from datetime import date, timedelta, datetime
from django.template.defaultfilters import register
from django.http import HttpResponseBadRequest, JsonResponse
import logging
from itertools import chain
from django.utils import timezone
from dashboard.models import Product
from django.core.paginator import Paginator
import json
from .utils import send_overdue_notification
from django.db import IntegrityError
from django.core.mail import send_mail
from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

@login_required
def index(request):
    """Dashboard home view"""
    today = date.today()
    last_week = today - timedelta(days=7)
    
    # Get all sales
    sales = Sale.objects.all()
    
    # Calculate total sales by multiplying price and quantity
    total_sales = sales.aggregate(
        total=Sum(F('price') * F('quantity'))
    )['total'] or Decimal('0.00')
    
    # Count total transactions
    total_transactions = sales.count()
    
    # Sum all quantities sold
    total_items = sales.aggregate(
        total=Sum('quantity')
    )['total'] or 0
    
    # Category distribution data
    categories = Product.objects.values('category').annotate(
        count=Count('id')
    ).order_by('category')
    
    # Ensure we have at least some default categories if none exist
    if not categories:
        categories = [
            {'category': 'Beverages', 'count': 0},
            {'category': 'Snacks', 'count': 0},
            {'category': 'Electronics', 'count': 0}
        ]
    
    # Serialize data to JSON strings
    category_labels = json.dumps([cat['category'] for cat in categories])
    category_counts = json.dumps([cat['count'] for cat in categories])
    
    # Sales trend data (last 7 days)
    sales_data = []
    for i in range(7):
        date_i = today - timedelta(days=i)
        daily_total = Sale.objects.filter(date__date=date_i).aggregate(
            total=Sum(F('price') * F('quantity'))  # Calculate daily total from price and quantity
        )['total'] or 0
        sales_data.append({
            'date__date': date_i,
            'total': float(daily_total)  # Convert Decimal to float for JSON serialization
        })
    
    sales_data.reverse()  # Show oldest to newest
    
    sales_dates = json.dumps([sale['date__date'].strftime('%b %d') for sale in sales_data])
    sales_amounts = json.dumps([sale['total'] for sale in sales_data])
    
    # Low stock alerts
    low_stock_items = Product.objects.filter(
        Q(stock__gt=0) & Q(stock__lte=5)
    ).order_by('stock')
    
    # Add borrower statistics with defaults
    borrower_stats = Borrower.objects.aggregate(
        active_count=Count('id', filter=Q(status='active')),
        paid_count=Count('id', filter=Q(status='paid')),
        overdue_count=Count('id', filter=Q(status='overdue'))
    )
    
    context = {
        'total_sales': total_sales,
        'total_transactions': total_transactions,
        'total_items_sold': total_items,
        'low_stock_items': low_stock_items,
        'category_labels': category_labels,
        'category_counts': category_counts,
        'sales_dates': sales_dates,
        'sales_amounts': sales_amounts,
        'borrower_active_count': borrower_stats['active_count'] or 0,
        'borrower_paid_count': borrower_stats['paid_count'] or 0,
        'borrower_overdue_count': borrower_stats['overdue_count'] or 0,
        'today': today,
    }
    
    return render(request, 'dashboard/index.html', context)


@login_required
def inventory(request):
    """Product inventory management view"""
    query = request.GET.get('q', '')
    category = request.GET.get('category', '')
    
    # Only show non-deleted products
    items = Product.objects.filter(is_deleted=False).order_by('name')
    
    if query:
        items = items.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query)
        )
    
    if category:
        items = items.filter(category=category)
    
    # Get categories as tuples with both value and display name
    categories = Product.CATEGORY
    
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            try:
                product_name = form.cleaned_data['name'].strip()
                # Double-check for existing product with same name (including soft-deleted ones)
                if Product.objects.filter(name__iexact=product_name).exists():
                    messages.error(request, f'A product with the name "{product_name}" already exists. Product names must be unique regardless of category.')
                    return render(request, 'dashboard/inventory.html', {
                        'items': items,
                        'form': form,
                        'categories': categories,
                        'current_category': category,
                        'search_query': query,
                    })
                
                with transaction.atomic():
                    product = form.save(commit=False)
                    product.name = product_name.title()  # Ensure consistent capitalization
                    product.save()
                    messages.success(request, 'Product added successfully!')
                return redirect('dashboard-inventory')
            except ValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Error adding product: {str(e)}')
        else:
            # Add form errors to messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = ProductForm()
        
    context = {
        'items': items,
        'form': form,
        'categories': categories,
        'current_category': category,
        'search_query': query,
    }
    return render(request, 'dashboard/inventory.html', context)


@login_required
def inventory_delete(request, pk):
    """Delete product view"""
    item = get_object_or_404(Product, id=pk)
    
    if request.method == 'POST':
        try:
            # Check if the product has any sales
            if item.sales.exists():
                # If it has sales, perform soft delete
                item.soft_delete()
                messages.success(request, 'Product has been archived successfully!')
            else:
                # If no sales, we can safely delete it
                item.delete()
                messages.success(request, 'Product deleted successfully!')
            return redirect('dashboard-inventory')
        except Exception as e:
            messages.error(request, f'Error deleting product: {str(e)}')
            return redirect('dashboard-inventory')
        
    return render(request, 'dashboard/inventory_delete.html', {'item': item})


@login_required
def inventory_update(request, pk):
    """Update product view"""
    item = get_object_or_404(Product.objects.filter(is_deleted=False), id=pk)
    
    if request.method == 'POST':
        # Check if this is a restock action
        if 'stock' in request.POST and not any(field for field in request.POST if field not in ['stock', 'csrfmiddlewaretoken']):
            try:
                with transaction.atomic():
                    # Get the additional stock amount
                    additional_stock = int(request.POST['stock'])
                    if additional_stock < 0:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({'success': False, 'error': 'Stock amount cannot be negative'})
                        messages.error(request, 'Stock amount cannot be negative')
                        return redirect('dashboard-inventory')
                    
                    # Update the stock
                    item.stock = F('stock') + additional_stock
                    item.save()
                    
                    # Refresh from db to get the new stock value
                    item.refresh_from_db()
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': f'Successfully added {additional_stock} units to stock',
                            'new_stock': item.stock
                        })
                    messages.success(request, f'Successfully added {additional_stock} units to stock')
                    return redirect('dashboard-inventory')
            except ValueError:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Invalid stock amount'})
                messages.error(request, 'Invalid stock amount')
                return redirect('dashboard-inventory')
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': str(e)})
                messages.error(request, f'Error updating stock: {str(e)}')
                return redirect('dashboard-inventory')
        
        # Regular update
        form = ProductForm(request.POST, instance=item)
        if form.is_valid():
            try:
                # Check for existing product with same name, excluding current product
                product_name = form.cleaned_data['name'].strip()
                if Product.objects.filter(name__iexact=product_name).exclude(id=pk).exists():
                    messages.error(request, f'A product with the name "{product_name}" already exists. Product names must be unique regardless of category.')
                    return render(request, 'dashboard/inventory_update.html', {
                        'item': item,
                        'form': form,
                    })
                
                with transaction.atomic():
                    product = form.save(commit=False)
                    product.name = product_name.title()  # Ensure consistent capitalization
                    product.save()
                    messages.success(request, 'Product updated successfully!')
                return redirect('dashboard-inventory')
            except Exception as e:
                messages.error(request, f'Error updating product: {str(e)}')
    else:
        form = ProductForm(instance=item)

    return render(request, 'dashboard/inventory_update.html', {
        'item': item,
        'form': form,
    })

@login_required
def sales_list(request):
    """Sales list view with proper timezone handling"""
    today = timezone.localtime().date()
    start_of_week = today - timedelta(days=7)
    
    # Create timezone-aware datetime objects
    start_datetime = timezone.make_aware(datetime.combine(start_of_week, datetime.min.time()))
    end_datetime = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    
    # Recent sales metrics
    recent_sales = Sale.objects.filter(date__range=(start_datetime, end_datetime))
    total_sales = recent_sales.aggregate(
        total=Sum(F('price') * F('quantity'))
    )['total'] or Decimal('0.00')
    
    # Get all sales ordered by date (newest first)
    sales_list = Sale.objects.all().order_by('-date')
    
    # Search functionality
    if q := request.GET.get('q'):
        sales_list = sales_list.filter(
            Q(product__name__icontains=q) |
            Q(buyer_name__icontains=q) |
            Q(date__date__icontains=q)
        )
    
    # Handle POST request (new sale)
    if request.method == 'POST':
        form = SaleForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                sale = form.save(commit=False)
                sale.recorded_by = request.user
                sale.date = timezone.now()
                sale.save()
                messages.success(request, f"Sale recorded successfully! Total: ₱{sale.total:.2f}")
                return redirect('dashboard-sales')
            except Exception as e:
                messages.error(request, f"Error recording sale: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SaleForm(user=request.user)
    
    # Pagination
    paginator = Paginator(sales_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'recent_sales': page_obj,
        'total_sales': total_sales,
        'total_transactions': sales_list.count(),
        'total_items_sold': sales_list.aggregate(Sum('quantity'))['quantity__sum'] or 0,
        'products': Product.objects.filter(stock__gt=0),
        'form': form,
    }
    return render(request, 'dashboard/sales.html', context)

@login_required 
def sales_edit(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    original_quantity = sale.quantity
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                product = Product.objects.select_for_update().get(pk=sale.product.pk)
                post_data = request.POST.copy()
                post_data['product'] = product.pk
                
                form = SaleForm(post_data, instance=sale, user=request.user)
                
                if form.is_valid():
                    new_quantity = form.cleaned_data['quantity']
                    quantity_diff = new_quantity - original_quantity
                    total_available = product.stock + original_quantity
                    
                    if new_quantity > total_available:
                        messages.error(request, f'Not enough stock. Only {total_available} units available.')
                    else:
                        product.stock = product.stock - quantity_diff
                        product.save()
                        
                        updated_sale = form.save(commit=False)
                        updated_sale.price = product.price
                        updated_sale.save()
                        
                        messages.success(request, 'Sale updated successfully!')
                        return redirect('dashboard-sales')
                else:
                    messages.error(request, 'Please correct the errors below.')
                    
        except Exception as e:
            messages.error(request, f"Error updating sale: {str(e)}")
    else:
        form = SaleForm(instance=sale, user=request.user)
    
    current_stock = sale.product.stock + original_quantity
    
    context = {
        'form': form,
        'sale': sale,
        'title': 'Edit Sale',
        'original_quantity': original_quantity,
        'available_stock': current_stock,
    }
    return render(request, 'dashboard/sales_edit.html', context)

@login_required
def sales_delete(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    
    if request.method == 'POST':
        # Restore product stock before deletion
        sale.product.stock += sale.quantity
        sale.product.save()
        sale.delete()
        messages.success(request, "Sale record deleted successfully!")
        return redirect('dashboard-sales')
    
    context = {
        'sale': sale,
    }
    
    return render(request, 'dashboard/sales_delete.html', context)

@login_required
def borrower_list(request):
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    
    today = timezone.now().date()
    
    # Base queryset with select_related for optimization
    borrowers = Borrower.objects.all()
    
    # Apply search filter
    if search_query:
        borrowers = borrowers.filter(
            Q(borrower_name__icontains=search_query) |
            Q(contact_number__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Update overdue status for active borrowers
    Borrower.objects.filter(
        Q(status='active'),
        due_date__lte=today
    ).exclude(
        status='paid'
    ).update(status='overdue')
    
    # Apply status filter after updating statuses
    if status_filter:
        borrowers = borrowers.filter(status=status_filter)
    
    # Order by status (overdue first) and due date
    borrowers = borrowers.order_by(
        Case(
            When(status='overdue', then=0),
            When(status='active', then=1),
            When(status='paid', then=2),
            default=3
        ),
        'due_date'
    )
    
    context = {
        'borrowers': borrowers,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    return render(request, 'dashboard/borrower_list.html', context)


@login_required
def borrower_create(request):
    """Create new borrower with styled form"""
    today = timezone.localtime().date()
    min_due_date = today + timedelta(days=1)
    
    if request.method == 'POST':
        logger.info("Received POST request to create borrower")
        logger.debug(f"POST data: {request.POST}")
        logger.debug(f"FILES data: {request.FILES}")
        
        form = BorrowerForm(request.POST, request.FILES)
        logger.info("Form initialized with POST data")
        
        if form.is_valid():
            logger.info("Form is valid, attempting to save")
            try:
                with transaction.atomic():
                    borrower_name = form.cleaned_data['borrower_name'].title()
                    logger.debug(f"Processing borrower name: {borrower_name}")
                    
                    if Borrower.objects.filter(borrower_name__iexact=borrower_name).exists():
                        logger.warning(f"Borrower with name '{borrower_name}' already exists")
                        error_msg = f'A borrower with the name "{borrower_name}" already exists.'
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'success': False,
                                'errors': {'borrower_name': [error_msg]}
                            }, status=400)
                        form.add_error('borrower_name', error_msg)
                        return render(request, 'dashboard/borrower_form.html', {
                            'form': form,
                            'today': today,
                            'min_due_date': min_due_date,
                            'title': 'Add Borrower'
                        })
                    
                    borrower = form.save(commit=False)
                    borrower.borrower_name = borrower_name
                    
                    if 'signature' in request.FILES:
                        logger.info("Processing signature file")
                        try:
                            borrower.signature = request.FILES['signature']
                            logger.info("Signature file assigned successfully")
                        except Exception as e:
                            logger.error(f"Error processing signature file: {str(e)}")
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return JsonResponse({
                                    'success': False,
                                    'errors': {'signature': [f'Error uploading signature: {str(e)}']}
                                }, status=400)
                            form.add_error('signature', f'Error uploading signature: {str(e)}')
                            raise
                    
                    try:
                        borrower.save()
                        logger.info(f"Borrower '{borrower_name}' created successfully with ID {borrower.pk}")
                    except Exception as e:
                        logger.error(f"Error saving borrower: {str(e)}")
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'success': False,
                                'errors': {'__all__': [f'Error saving borrower: {str(e)}']}
                            }, status=400)
                        raise
                    
                    messages.success(request, f'Borrower "{borrower_name}" created successfully!')
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': f'Borrower "{borrower_name}" created successfully!',
                            'redirect_url': reverse('dashboard-borrower-detail', kwargs={'pk': borrower.pk})
                        })
                    return redirect('dashboard-borrower-detail', pk=borrower.pk)
                    
            except IntegrityError as e:
                logger.error(f"IntegrityError while creating borrower: {str(e)}")
                error_msg = f'A borrower with the name "{borrower_name}" already exists.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': {'borrower_name': [error_msg]}
                    }, status=400)
                messages.error(request, error_msg)
            except Exception as e:
                logger.error(f"Unexpected error while creating borrower: {str(e)}")
                error_msg = f'Error creating borrower: {str(e)}'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': {'__all__': [error_msg]}
                    }, status=400)
                messages.error(request, error_msg)
        else:
            logger.warning("Form validation failed")
            logger.debug(f"Form errors: {form.errors}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
    else:
        logger.info("Displaying empty borrower creation form")
        form = BorrowerForm(initial={
            'date_borrowed': today,
            'due_date': min_due_date
        })
    
    context = {
        'form': form,
        'today': today,
        'min_due_date': min_due_date,
        'title': 'Add Borrower'
    }
    return render(request, 'dashboard/borrower_form.html', context)

@login_required
def borrower_detail(request, pk):
    borrower = get_object_or_404(Borrower, pk=pk)
    items = BorrowedItem.objects.filter(borrower=borrower)
    
    if request.method == 'POST':
        form = BorrowedItemForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    borrowed_item = form.save(commit=False)
                    borrowed_item.borrower = borrower
                    borrowed_item.price = borrowed_item.product.price
                    
                    # Check stock
                    if borrowed_item.product.stock < borrowed_item.quantity:
                        messages.error(request, f'Not enough stock. Only {borrowed_item.product.stock} available.')
                        return redirect('dashboard-borrower-detail', pk=pk)
                    
                    # Update stock and save
                    borrowed_item.product.stock -= borrowed_item.quantity
                    borrowed_item.product.save()
                    borrowed_item.save()
                    
                    messages.success(request, 'Item added successfully!')
            except Exception as e:
                messages.error(request, f'Error: {str(e)}')
    else:
        form = BorrowedItemForm()
    
    context = {
        'borrower': borrower,
        'items': items,
        'form': form
    }
    return render(request, 'dashboard/borrower_detail.html', context)


@login_required
def borrower_update(request, pk):
    """Update borrower view"""
    # Use select_related to optimize queries
    borrower = get_object_or_404(
        Borrower.objects.select_related(),
        pk=pk
    )
    
    if request.method == 'POST':
        form = BorrowerForm(request.POST, request.FILES, instance=borrower)
        if form.is_valid():
            try:
                with transaction.atomic():
                    borrower = form.save(commit=False)
                    
                    # Handle signature removal
                    if request.POST.get('remove_signature') == 'on':
                        if borrower.signature:
                            borrower.signature.delete(save=False)
                            borrower.signature = None
                    
                    # Handle new signature upload
                    elif 'signature' in request.FILES:
                        if borrower.signature:
                            borrower.signature.delete(save=False)
                        borrower.signature = request.FILES['signature']
                    
                    borrower.save()
                    messages.success(request, f'Successfully updated {borrower.borrower_name}')
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True})
                    return redirect('dashboard-borrower-detail', pk=borrower.pk)
            
            except Exception as e:
                error_msg = f'Error updating borrower: {str(e)}'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'errors': {'__all__': [error_msg]}}, status=400)
                messages.error(request, error_msg)
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'errors': form.errors}, status=400)
    else:
        form = BorrowerForm(instance=borrower)
    
    context = {
        'form': form,
        'borrower': borrower,
        'title': 'Update Borrower'
    }
    
    return render(request, 'dashboard/borrower_form.html', context)

@login_required
def borrower_delete(request, pk):
    borrower = get_object_or_404(Borrower, pk=pk)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                if borrower.status != 'paid':
                    for item in borrower.items.filter(is_returned=False):
                        item.product.stock += item.quantity
                        item.product.save()
                borrower.delete()
                messages.success(request, 'Borrower deleted successfully!')
                return redirect('dashboard-borrower-list')
        except Exception as e:
            messages.error(request, f'Error deleting borrower: {str(e)}')
            logger.exception("Error deleting borrower")
    
    return render(request, 'dashboard/borrower_confirm_delete.html', {'borrower': borrower})


@login_required
def mark_as_paid(request, pk):
    """Mark borrower as paid view"""
    borrower = get_object_or_404(Borrower, pk=pk)
    try:
        with transaction.atomic():
            borrower.status = 'paid'
            borrower.save()
            messages.success(request, 'Marked as paid successfully!')
    except Exception as e:
        messages.error(request, f'Error marking as paid: {str(e)}')
        logger.exception("Error marking borrower as paid")
    
    return redirect('dashboard-borrower-detail', pk=pk)


@login_required
def mark_as_returned(request, item_id):
    """Mark borrowed item as returned view"""
    item = get_object_or_404(BorrowedItem, id=item_id)
    borrower_pk = item.borrower.pk
    
    try:
        with transaction.atomic():
            if not item.is_returned:
                # Return the item to stock
                Product.objects.filter(pk=item.product.id).update(
                    stock=F('stock') + item.quantity
                )
                item.is_returned = True
                item.date_returned = timezone.now().date()
                item.save()
                messages.success(request, 'Item marked as returned!')
            else:
                messages.warning(request, 'Item was already returned')
    except Exception as e:
        messages.error(request, f'Error marking item as returned: {str(e)}')
        logger.exception("Error marking item as returned")
    
    return redirect('dashboard-borrower-detail', pk=borrower_pk)


@login_required
def borrowed_item_delete(request, pk):
    item = get_object_or_404(BorrowedItem, pk=pk)
    borrower_pk = item.borrower.pk
    deleted_quantity = item.quantity
    
    try:
        with transaction.atomic():
            # Get the product and update its stock
            product = Product.objects.select_for_update().get(pk=item.product.pk)
            product.stock += deleted_quantity
            product.save()
            
            # Delete the borrowed item
            item.delete()
            
            messages.success(
                request, 
                f'Item deleted and {deleted_quantity} units returned to inventory.'
            )
    except Product.DoesNotExist:
        messages.error(request, 'Error: Product not found')
    except Exception as e:
        messages.error(request, f'Error deleting item: {str(e)}')
    
    return redirect('dashboard-borrower-detail', pk=borrower_pk)


@login_required
def reports(request):
    """Reports generation view"""
    # Time period calculations
    today = date.today()
    last_week = today - timedelta(days=7)
    last_month = today - timedelta(days=30)
    
    # Sales reports
    daily_sales = Sale.objects.filter(date__date=today)
    weekly_sales = Sale.objects.filter(date__gte=last_week)
    monthly_sales = Sale.objects.filter(date__gte=last_month)
    
    # Calculate totals
    daily_total = daily_sales.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    weekly_total = weekly_sales.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    monthly_total = monthly_sales.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    # Top selling products
    top_products = Product.objects.annotate(
        total_sold=Sum('sales__quantity')
    ).order_by('-total_sold')[:5]
    
    # Borrowed items report
    overdue_items = BorrowedItem.objects.filter(
        is_returned=False,
        borrower__due_date__lt=today
    ).select_related('borrower', 'product')
    
    context = {
        'daily_sales': daily_sales,
        'weekly_sales': weekly_sales,
        'monthly_sales': monthly_sales,
        'daily_total': daily_total,
        'weekly_total': weekly_total,
        'monthly_total': monthly_total,
        'top_products': top_products,
        'overdue_items': overdue_items,
    }
    return render(request, 'dashboard/reports.html', context)


@register.filter
def filter_is_returned(items):
    """Template filter for returned items"""
    return [item for item in items if item.is_returned]


@login_required
def check_product_name(request):
    """Check if a product name already exists"""
    name = request.GET.get('name', '').strip().title()
    exists = Product.objects.filter(name__iexact=name).exists()
    return JsonResponse({'exists': exists})


@login_required
def check_overdue_borrowers(request):
    today = timezone.now().date()
    logger.info(f"Checking overdue borrowers for date: {today}")
    
    # Find all overdue borrowers with valid emails
    overdue_borrowers = Borrower.objects.filter(
        Q(status='active') | Q(status='overdue'),
        due_date__lte=today
    ).exclude(
        Q(status='paid') | 
        Q(email__isnull=True) | 
        Q(email='')
    )
    
    logger.info(f"Found {overdue_borrowers.count()} overdue borrowers")
    
    notifications_sent = 0
    notification_results = []  # Store results to display later
    
    for borrower in overdue_borrowers:
        try:
            if not borrower.email or not borrower.email.strip():
                logger.warning(f"Skipping {borrower.borrower_name} - No email address")
                notification_results.append(f"Skipped {borrower.borrower_name} - No email address")
                continue
                
            logger.info(f"Processing {borrower.borrower_name} with email {borrower.email}")
            
            subject = "OVERDUE PAYMENT NOTICE - Sari-Sari Store"
            message = (
                f"Dear {borrower.borrower_name},\n\n"
                f"Your loan payment of ₱{borrower.total_debt:,.2f} "
                f"was due on {borrower.due_date}.\n\n"
                f"Please settle your payment as soon as possible.\n\n"
                f"Best regards,\nSari-Sari Store"
            )
            
            # Send email
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[borrower.email.strip()],
                fail_silently=False,
            )
            
            # Update status if not already overdue
            if borrower.status != 'overdue':
                borrower.status = 'overdue'
                borrower.save(update_fields=['status'])
            
            notifications_sent += 1
            logger.info(f"Successfully sent notification to {borrower.email}")
            notification_results.append(f"Successfully sent notification to {borrower.borrower_name} ({borrower.email})")
            
        except Exception as e:
            error_msg = f"Failed to notify {borrower.borrower_name}: {str(e)}"
            logger.error(error_msg)
            notification_results.append(error_msg)
    
    # Add messages in bulk after processing all borrowers
    if notifications_sent > 0:
        messages.success(request, f'Successfully sent {notifications_sent} overdue notifications')
    else:
        if overdue_borrowers.exists():
            messages.warning(request, 'Found overdue borrowers but failed to send notifications')
        else:
            messages.info(request, 'No overdue borrowers found')
    
    # Add detailed results
    for result in notification_results:
        messages.info(request, result)
    
    return redirect('dashboard-borrower-list')


@login_required
def send_email_notifications(request):
    today = timezone.now().date()
    notifications_sent = 0

    try:
        # Get borrowers who are overdue and have valid emails
        overdue_borrowers = Borrower.objects.filter(
            Q(status='active') | Q(status='overdue'),
            due_date__lt=today,
            email__isnull=False
        ).exclude(email='')
        
        # Debug logging
        logger.info(f"Found {overdue_borrowers.count()} overdue borrowers with email")
        for borrower in overdue_borrowers:
            logger.info(f"Overdue borrower: {borrower.borrower_name}, Email: {borrower.email}, Due date: {borrower.due_date}")

        # Get borrowers with upcoming due dates (3 days warning)
        upcoming_due = Borrower.objects.filter(
            status='active',
            due_date=today + timedelta(days=3),
            email__isnull=False
        ).exclude(email='')
        
        # Debug logging
        logger.info(f"Found {upcoming_due.count()} due soon borrowers with email")
        for borrower in upcoming_due:
            logger.info(f"Due soon borrower: {borrower.borrower_name}, Email: {borrower.email}, Due date: {borrower.due_date}")

        # Process overdue notifications
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

                logger.info(f"Attempting to send overdue email to {borrower.email}")
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
                logger.info(f"Successfully sent overdue email to {borrower.email}")

            except Exception as e:
                logger.error(f"Failed to send overdue notification to {borrower.borrower_name}: {str(e)}")
                messages.error(
                    request,
                    f"Failed to send overdue notification to {borrower.borrower_name}: {str(e)}"
                )

        # Process upcoming due date notifications
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

                logger.info(f"Attempting to send due soon email to {borrower.email}")
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[borrower.email],
                    fail_silently=False,
                )

                notifications_sent += 1
                logger.info(f"Successfully sent due soon email to {borrower.email}")

            except Exception as e:
                logger.error(f"Failed to send reminder to {borrower.borrower_name}: {str(e)}")
                messages.error(
                    request,
                    f"Failed to send reminder to {borrower.borrower_name}: {str(e)}"
                )

        if notifications_sent > 0:
            messages.success(request, f"Successfully sent {notifications_sent} notifications")
        else:
            logger.info("No notifications sent. Debug info:")
            logger.info(f"- Overdue borrowers: {overdue_borrowers.count()}")
            logger.info(f"- Due soon borrowers: {upcoming_due.count()}")
            logger.info(f"Current date: {today}")
            messages.info(request, "No notifications to send at this time")

        return redirect('dashboard-borrower-list')

    except Exception as e:
        logger.error(f"Error in send_email_notifications: {str(e)}")
        messages.error(request, f"Error sending notifications: {str(e)}")
        return redirect('dashboard-borrower-list')


@user_passes_test(lambda u: u.is_superuser)
def test_email(request):
    try:
        send_mail(
            'Test Email from Sari-Sari Store',
            'This is a test email to verify the email configuration.',
            settings.EMAIL_HOST_USER,
            [settings.EMAIL_HOST_USER],  # Send to yourself
            fail_silently=False,
        )
        messages.success(request, 'Test email sent successfully!')
    except Exception as e:
        messages.error(request, f'Failed to send test email: {str(e)}')
    return redirect('dashboard-index')

@login_required
def inventory_audit(request):
    """View for conducting inventory audits"""
    if request.method == 'POST':
        product_id = request.POST.get('product')
        physical_count = request.POST.get('physical_count')
        notes = request.POST.get('notes', '')

        try:
            with transaction.atomic():
                product = Product.objects.select_for_update().get(id=product_id)
                
                # Create audit record
                audit = InventoryAudit.objects.create(
                    product=product,
                    system_count=product.stock,
                    physical_count=int(physical_count),
                    notes=notes,
                    conducted_by=request.user
                )

                if request.POST.get('adjust_immediately'):
                    audit.adjust_inventory()
                    messages.success(request, f'Inventory adjusted for {product.name}. Discrepancy: {audit.discrepancy}')
                else:
                    messages.info(request, f'Audit recorded for {product.name}. Discrepancy: {audit.discrepancy}')

                return redirect('dashboard-inventory')

        except Product.DoesNotExist:
            messages.error(request, 'Product not found.')
        except ValueError:
            messages.error(request, 'Invalid count value provided.')
        except Exception as e:
            messages.error(request, f'Error during audit: {str(e)}')

    # Get products for audit
    products = Product.objects.filter(is_deleted=False).order_by('name')
    pending_audits = InventoryAudit.objects.filter(adjusted=False).select_related('product')

    context = {
        'products': products,
        'pending_audits': pending_audits,
    }
    return render(request, 'dashboard/inventory_audit.html', context)

@login_required
def audit_history(request):
    """View audit history"""
    audits = InventoryAudit.objects.all().select_related('product', 'conducted_by')
    
    # Filter by date range
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date and end_date:
        try:
            start = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
            audits = audits.filter(audit_date__range=[start, end])
        except ValueError:
            messages.error(request, 'Invalid date format')
    
    # Calculate summary statistics
    total_audits = audits.count()
    total_discrepancies = audits.aggregate(
        total=Sum('discrepancy'),
        absolute_total=Sum(Abs('discrepancy'))
    )
    
    context = {
        'audits': audits,
        'total_audits': total_audits,
        'total_discrepancies': total_discrepancies,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'dashboard/audit_history.html', context)

@login_required
def resolve_audit(request, audit_id):
    """Resolve pending audit by adjusting inventory"""
    audit = get_object_or_404(InventoryAudit, id=audit_id, adjusted=False)
    
    try:
        with transaction.atomic():
            audit.adjust_inventory()
            messages.success(request, f'Successfully adjusted inventory for {audit.product.name}')
    except Exception as e:
        messages.error(request, f'Error adjusting inventory: {str(e)}')
    
    return redirect('dashboard-inventory-audit')

@login_required
def download_audit_report(request):
    """Download audit report as CSV"""
    import csv
    from django.http import HttpResponse
    from datetime import datetime

    # Get date range filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Query audits with filters
    audits = InventoryAudit.objects.all().select_related('product', 'conducted_by')
    
    if start_date and end_date:
        try:
            start = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
            audits = audits.filter(audit_date__range=[start, end])
        except ValueError:
            messages.error(request, 'Invalid date format')
    
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="audit_report_{timestamp}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    writer.writerow([
        'Date',
        'Product',
        'System Count',
        'Physical Count',
        'Discrepancy',
        'Status',
        'Conducted By',
        'Notes'
    ])
    
    # Write data
    for audit in audits:
        writer.writerow([
            audit.audit_date.strftime('%Y-%m-%d %H:%M'),
            audit.product.name,
            audit.system_count,
            audit.physical_count,
            audit.discrepancy,
            'Adjusted' if audit.adjusted else 'Pending',
            audit.conducted_by.username,
            audit.notes
        ])
    
    return response

@login_required
def download_audit_report_excel(request):
    """Download audit report as Excel"""
    import xlsxwriter
    from io import BytesIO
    from datetime import datetime
    from django.http import HttpResponse
    from django.utils import timezone

    # Get date range filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Query audits with filters
    audits = InventoryAudit.objects.all().select_related('product', 'conducted_by')
    
    if start_date and end_date:
        try:
            start = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
            audits = audits.filter(audit_date__range=[start, end])
        except ValueError:
            messages.error(request, 'Invalid date format')

    # Create a BytesIO buffer for the Excel file
    buffer = BytesIO()
    
    # Create Excel workbook and add a worksheet
    workbook = xlsxwriter.Workbook(buffer, {'remove_timezone': True})  # Add remove_timezone option
    worksheet = workbook.add_worksheet('Audit Report')
    
    # Add formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#04AA6D',
        'color': 'white',
        'border': 1
    })
    
    date_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm'})
    cell_format = workbook.add_format({'border': 1})
    
    # Write headers
    headers = [
        'Date',
        'Product',
        'System Count',
        'Physical Count',
        'Discrepancy',
        'Status',
        'Conducted By',
        'Notes'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)
        worksheet.set_column(col, col, 15)  # Set column width
    
    # Write data
    for row, audit in enumerate(audits, start=1):
        # Convert timezone-aware datetime to naive datetime
        naive_date = timezone.localtime(audit.audit_date).replace(tzinfo=None)
        worksheet.write(row, 0, naive_date, date_format)
        worksheet.write(row, 1, audit.product.name, cell_format)
        worksheet.write(row, 2, audit.system_count, cell_format)
        worksheet.write(row, 3, audit.physical_count, cell_format)
        worksheet.write(row, 4, audit.discrepancy, cell_format)
        worksheet.write(row, 5, 'Adjusted' if audit.adjusted else 'Pending', cell_format)
        worksheet.write(row, 6, audit.conducted_by.username, cell_format)
        worksheet.write(row, 7, audit.notes or '', cell_format)
    
    # Close the workbook
    workbook.close()
    
    # Create the HttpResponse
    buffer.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="audit_report_{timestamp}.xlsx"'
    
    return response