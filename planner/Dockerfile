FROM python:3.11-slim

WORKDIR /app

COPY planner/requirements.txt /app/planner_requirements.txt
RUN pip install --no-cache-dir -r planner_requirements.txt

COPY common /app/common
COPY planner /app/planner

ENV PYTHONPATH=/app

CMD ["python", "-m", "planner.main"]
