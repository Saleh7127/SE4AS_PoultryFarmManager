FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# We need DbManager.py from monitor... 
# Ideally we'd package it, but for now we will cheat in docker-compose or copy it.
# Wait, I cannot copy from another dir in Docker build context unless it's parent.
# I will have to copy DbManager.py into src/analyzer/ locally first.
COPY . .

CMD ["python", "main.py"]
