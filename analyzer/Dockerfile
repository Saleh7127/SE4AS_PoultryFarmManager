FROM python:3.11-slim

WORKDIR /app

COPY analyzer/requirements.txt /app/analyzer_requirements.txt
RUN pip install --no-cache-dir -r analyzer_requirements.txt

COPY common /app/common
COPY analyzer /app/analyzer

ENV PYTHONPATH=/app

CMD ["python", "-m", "analyzer.main"]
