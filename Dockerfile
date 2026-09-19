FROM python:3.12-slim
WORKDIR /app
COPY xmind_deploy.zip /tmp/xmind_deploy.zip
RUN python -m zipfile -e /tmp/xmind_deploy.zip /app \
    && pip install --no-cache-dir . \
    && rm /tmp/xmind_deploy.zip
EXPOSE 8000
CMD ["sh", "-c", "uvicorn xmind.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
