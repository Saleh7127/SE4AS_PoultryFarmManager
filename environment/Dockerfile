FROM python:3.11-slim

WORKDIR /app

COPY environment/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy shared common code
COPY common /app/common
COPY environment /app/environment

ENV PYTHONPATH=/app

CMD ["python", "-m", "environment.main"]
