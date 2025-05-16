#!/usr/bin/env python
import os
import sys
from pathlib import Path

def main():
    """Run administrative tasks."""
    # Add the project directory to Python path
    project_dir = Path(__file__).resolve().parent
    sys.path.append(str(project_dir))
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Sari_Sari_IMS.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
