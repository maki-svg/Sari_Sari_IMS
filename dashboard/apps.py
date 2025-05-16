from django.apps import AppConfig

class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        """Initialize app when ready"""
        # Import signals module to connect signal handlers
        from . import signals  # Relative import