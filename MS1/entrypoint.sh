#!/bin/sh

# This is the specialized entrypoint script for the MS1 (Auth Service).

# 1. Apply database migrations for the 'accounts' app first.
echo "Applying 'accounts' app migrations..."
python manage.py makemigrations accounts --noinput
python manage.py migrate accounts --noinput

# 2. Apply all remaining database migrations.
# This will handle other apps like 'contenttypes', 'admin', 'sessions', and your 'messaging' app.
# Django is smart enough not to re-apply the 'accounts' migrations.
echo "Applying remaining migrations..."
python manage.py makemigrations
python manage.py migrate 

# 3. Execute the main command passed to the container.
echo "Migrations complete. Starting the main process..."



# Check if the command is our placeholder "run-gunicorn"
if [ "$1" = "run-gunicorn" ]; then
    # Start Gunicorn. The shell will correctly expand $DJANGO_PROJECT_NAME.
    echo "Starting Gunicorn server for project: ${DJANGO_PROJECT_NAME}"
    exec gunicorn --workers 4 --bind 0.0.0.0:8000 "${DJANGO_PROJECT_NAME}.wsgi:application"
else
    # If the command is not the placeholder (e.g., a worker command), execute it directly.
    exec "$@"
fi