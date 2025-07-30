#!/bin/sh

# This is the standard entrypoint script for general services.

# 1. Apply database migrations
echo "Applying database migrations..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# 2. Execute the main command passed to the container
echo "Migrations complete. Starting the main process..."
#!/bin/sh

set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Migrations complete."

# Check if the command is our placeholder "run-gunicorn"
if [ "$1" = "run-gunicorn" ]; then
    # Start Gunicorn. The shell will correctly expand $DJANGO_PROJECT_NAME.
    echo "Starting Gunicorn server for project: ${DJANGO_PROJECT_NAME}"
    exec gunicorn --workers 4 --bind 0.0.0.0:8000 "${DJANGO_PROJECT_NAME}.wsgi:application"
else
    # If the command is not the placeholder (e.g., a worker command), execute it directly.
    exec "$@"
fi