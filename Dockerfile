FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY app.py .
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "flask --app app:create_app init-db && exec gunicorn --bind 0.0.0.0:8000 --workers 2 --access-logfile - 'app:create_app()'"]
