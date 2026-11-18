FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -r -u 10001 ktm && mkdir -p /data && chown -R ktm:ktm /app /data
USER ktm
EXPOSE 8080
CMD ["sh", "-c", "python -c 'from app import init_db; init_db()' && waitress-serve --listen=0.0.0.0:${PORT:-8080} app:app"]
