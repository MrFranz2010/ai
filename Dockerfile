FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py render_start.py supabase_store.py ./
COPY web/ ./web/

EXPOSE 10000
CMD ["python", "render_start.py"]
