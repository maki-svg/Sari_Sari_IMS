from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Count
import random
import string


def generate_unique_suffix():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))


def remove_constraint_if_exists(apps, schema_editor):
    # Get the cursor
    cursor = schema_editor.connection.cursor()
    
    # Check if the constraint exists
    cursor.execute("""
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE constraint_name = 'unique_borrower_name_per_user'
        AND table_name = 'dashboard_borrower';
    """)
    
    if cursor.fetchone():
        # If it exists, drop it
        cursor.execute('ALTER TABLE dashboard_borrower DROP CONSTRAINT unique_borrower_name_per_user;')


def fix_duplicate_borrowers(apps, schema_editor):
    # First remove any existing constraint
    remove_constraint_if_exists(apps, schema_editor)
    
    Borrower = apps.get_model('dashboard', 'Borrower')
    User = apps.get_model('auth', 'User')
    
    # Get the first superuser or create one if none exists
    default_user = User.objects.filter(is_superuser=True).first()
    if not default_user:
        default_user = User.objects.first()
    
    if default_user:
        # First, update all borrowers with NULL user
        Borrower.objects.filter(user__isnull=True).update(user=default_user)
        
        # Now find and fix duplicates
        duplicates = (
            Borrower.objects
            .values('user_id', 'borrower_name')
            .annotate(name_count=Count('id'))
            .filter(name_count__gt=1)
        )
        
        # For each set of duplicates
        for duplicate in duplicates:
            # Get all borrowers with this name except the first one
            borrowers = (
                Borrower.objects
                .filter(
                    user_id=duplicate['user_id'],
                    borrower_name=duplicate['borrower_name']
                )
                .order_by('id')[1:]  # Skip the first one
            )
            
            # Update each duplicate with a unique name
            for borrower in borrowers:
                while True:
                    new_name = f"{borrower.borrower_name} ({generate_unique_suffix()})"
                    if not Borrower.objects.filter(user_id=borrower.user_id, borrower_name=new_name).exists():
                        borrower.borrower_name = new_name
                        borrower.save()
                        break


def reverse_fix_duplicate_borrowers(apps, schema_editor):
    pass  # We can't easily reverse this operation


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        # First run the function to fix duplicates and assign default user
        migrations.RunPython(
            fix_duplicate_borrowers,
            reverse_fix_duplicate_borrowers
        ),
        
        # Then modify the field to be non-nullable
        migrations.AlterField(
            model_name='borrower',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='borrowers',
                to='auth.user'
            ),
        ),
        
        # Finally, add the unique constraint
        migrations.AddConstraint(
            model_name='borrower',
            constraint=models.UniqueConstraint(
                fields=['user', 'borrower_name'],
                name='unique_borrower_name_per_user'
            ),
        ),
    ] 