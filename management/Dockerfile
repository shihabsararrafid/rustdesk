FROM python:3.14.2-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /service
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock \
    && apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 management \
    && useradd --uid 10001 --gid 10001 --no-create-home management \
    && mkdir /data /media && chown 10001:10001 /data /media
COPY app ./app
COPY static ./static
COPY smoke.py .
USER 10001:10001
EXPOSE 21114
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "21114", "--workers", "1", "--no-proxy-headers", "--no-access-log"]
