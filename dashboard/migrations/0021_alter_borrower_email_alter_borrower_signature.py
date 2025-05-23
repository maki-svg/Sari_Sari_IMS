# Generated by Django 4.2.21 on 2025-05-16 20:04

import cloudinary.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0020_inventoryaudit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='borrower',
            name='email',
            field=models.EmailField(blank=True, error_messages={'invalid': 'Please enter a valid email address.'}, help_text='Email address for notifications', max_length=254, null=True),
        ),
        migrations.AlterField(
            model_name='borrower',
            name='signature',
            field=cloudinary.models.CloudinaryField(blank=True, help_text="Upload borrower's signature (optional)", max_length=255, null=True, verbose_name='signature'),
        ),
    ]
