from django.db import migrations

def assign_sales_to_product_owners(apps, schema_editor):
    Sale = apps.get_model('dashboard', 'Sale')
    
    # Update all sales to be owned by the product owner
    for sale in Sale.objects.filter(user__isnull=True):
        sale.user = sale.product.user
        sale.save()

def reverse_func(apps, schema_editor):
    # No need to reverse this operation
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0026_alter_sale_user_sale_dashboard_s_date_b76b1d_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(assign_sales_to_product_owners, reverse_func),
    ] 