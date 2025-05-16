from django.urls import path
from . import views
from django.contrib.auth.decorators import login_required

urlpatterns = [
    path('', login_required(views.index), name='dashboard-index'),
    path('inventory/', login_required(views.inventory), name='dashboard-inventory'),
    path('inventory/delete/<int:pk>/', login_required(views.inventory_delete), name='dashboard-inventory-delete'),
    path('inventory/update/<int:pk>/', login_required(views.inventory_update), name='dashboard-inventory-update'),
    path('inventory/audit/', login_required(views.inventory_audit), name='dashboard-inventory-audit'),
    path('inventory/audit/history/', login_required(views.audit_history), name='dashboard-audit-history'),
    path('inventory/audit/resolve/<int:audit_id>/', login_required(views.resolve_audit), name='dashboard-resolve-audit'),
    path('sales/', login_required(views.sales_list), name='dashboard-sales'),
    path('sales/edit/<int:pk>/', login_required(views.sales_edit), name='dashboard-sales-edit'),
    path('sales/delete/<int:pk>/', login_required(views.sales_delete), name='dashboard-sales-delete'),
    path('borrowers/', login_required(views.borrower_list), name='dashboard-borrower-list'),
    path('borrowers/add/', login_required(views.borrower_create), name='dashboard-borrower-create'),
    path('borrowers/<int:pk>/', login_required(views.borrower_detail), name='dashboard-borrower-detail'),
    path('borrowers/<int:pk>/edit/', login_required(views.borrower_update), name='dashboard-borrower-update'),
    path('borrowers/<int:pk>/delete/', login_required(views.borrower_delete), name='dashboard-borrower-delete'),
    path('borrowers/<int:pk>/paid/', login_required(views.mark_as_paid), name='dashboard-borrower-paid'),
    path('borrowers/items/<int:pk>/delete/', login_required(views.borrowed_item_delete), name='dashboard-borrower-item-delete'),
    path('check-product-name/', login_required(views.check_product_name), name='check-product-name'),
    path('check-overdue/', login_required(views.check_overdue_borrowers), name='check-overdue'),
    path('send-notifications/', login_required(views.send_email_notifications), name='send-notifications'),
    path('inventory/audit/download/csv/', login_required(views.download_audit_report), name='dashboard-audit-download-csv'),
    path('inventory/audit/download/excel/', login_required(views.download_audit_report_excel), name='dashboard-audit-download-excel'),
]