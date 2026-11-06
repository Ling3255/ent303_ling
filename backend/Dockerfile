FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 需要 bge-m3 时：docker compose build --build-arg WITH_EMBED=1 backend
ARG WITH_EMBED=0
COPY requirements-embed.txt .
RUN if [ "$WITH_EMBED" = "1" ]; then pip install --no-cache-dir -r requirements-embed.txt; fi
COPY app ./app
COPY eval ./eval
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
