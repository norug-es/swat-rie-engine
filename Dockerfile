FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system rie && adduser --system --ingroup rie rie \
    && mkdir -p /app/data && chown -R rie:rie /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=rie:rie app ./app
COPY --chown=rie:rie tests ./tests

USER rie
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
