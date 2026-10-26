FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY back/ back/
COPY data/docs/ data/docs/
RUN mkdir -p storage

EXPOSE 8000

CMD ["python", "back/Server.py"]
