FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DJANGO_SECRET_KEY=build-only-key
RUN PAYMENT_GATEWAY_MODE=mock python manage.py collectstatic --noinput
ENV DJANGO_SECRET_KEY=
ENV WEB_CONCURRENCY=3
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && exec uvicorn backend.asgi:application --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-3}"]
