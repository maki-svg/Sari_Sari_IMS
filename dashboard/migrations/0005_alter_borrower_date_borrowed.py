# Generated by Django 5.1.5 on 2025-04-04 10:02

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0004_alter_borrower_due_date'),
    ]

    operations = [
        migrations.AlterField(
            model_name='borrower',
            name='date_borrowed',
            field=models.DateField(default=django.utils.timezone.now),
        ),
    ]
