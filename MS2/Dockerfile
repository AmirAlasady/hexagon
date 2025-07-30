FROM ai_engine_base:latest

WORKDIR /app

# --- THE FIX IS HERE ---
# ARG declares a build-time variable that can be passed from docker-compose.
ARG DJANGO_PROJECT_NAME
# ENV makes the value of the ARG available as an environment variable at runtime.
ENV DJANGO_PROJECT_NAME=${DJANGO_PROJECT_NAME}
# ---------------------

# Copy the service's specific files
COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh
COPY . .

# Run collectstatic (this part is correct)
RUN DJANGO_SECRET_KEY="dummy" python manage.py collectstatic --noinput

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["run-gunicorn"]