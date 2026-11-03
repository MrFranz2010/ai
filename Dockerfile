FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py fly_start.py ./
COPY web/ ./web/

EXPOSE 8080
CMD ["python", "fly_start.py"]
