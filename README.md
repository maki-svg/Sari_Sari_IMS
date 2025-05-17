# SariSync - Sari-Sari Store Inventory Management System

A comprehensive inventory management system designed for Sari-Sari stores, helping small business owners manage their inventory, sales, and borrower records efficiently.

## Features

- Inventory Management
- Sales Tracking
- Borrower Management
- Audit History
- User Authentication
- Responsive Design

## Tech Stack

- Django 4.2
- Bootstrap 5
- SQLite (Development) / PostgreSQL (Production)
- Crispy Forms
- WhiteNoise for static files
- Gunicorn for production server

## Local Development Setup

1. Clone the repository
```bash
git clone https://github.com/maki-svg/Sari_Sari_IMS.git
cd Sari_Sari_IMS
```

2. Create a virtual environment
```bash
python -m venv env
source env/bin/activate  # On Windows use: env\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Run migrations
```bash
python manage.py migrate
```

5. Create a superuser
```bash
python manage.py createsuperuser
```

6. Run the development server
```bash
python manage.py runserver
```

## Deployment

This application is configured for deployment on Render. Make sure to:

1. Set up a PostgreSQL database on Render
2. Configure the following environment variables:
   - `DATABASE_URL`
   - `SECRET_KEY`
   - `DEBUG=False`
   - `ALLOWED_HOSTS`

## License

This project is licensed under the MIT License - see the LICENSE file for details. 