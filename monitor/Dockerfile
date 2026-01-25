FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY monitor/requirements.txt /app/monitor_requirements.txt
RUN pip install --no-cache-dir -r monitor_requirements.txt

# Copy shared common code and monitor package
COPY common /app/common
COPY monitor /app/monitor

ENV PYTHONPATH=/app

CMD ["python", "-m", "monitor.main"]
