FROM python:3.13-slim

WORKDIR /app

RUN mkdir /data && chown 10001:10001 /data

COPY app.py VERSION ./

ENV PYTHONUNBUFFERED=1 \
    CRUD_DB_PATH=/data/items.db

USER 10001:10001

EXPOSE 8000

CMD ["python", "app.py", "--host", "0.0.0.0"]
