FROM python:3.11-slim

WORKDIR /app

COPY executor/requirements.txt /app/executor_requirements.txt
RUN pip install --no-cache-dir -r executor_requirements.txt

COPY common /app/common
COPY executor /app/executor

ENV PYTHONPATH=/app

CMD ["python", "-m", "executor.main"]