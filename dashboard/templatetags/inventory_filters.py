from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def count_low_stock(items):
    """Count items with stock less than or equal to 5"""
    return sum(1 for item in items if item.stock <= 5)

@register.filter
def sum_stock_value(items):
    """Calculate total value of all items in stock"""
    return sum(item.stock * item.price for item in items)