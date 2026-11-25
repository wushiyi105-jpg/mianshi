FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8771

CMD ["python", "-m", "mianshi", "web", "--host", "0.0.0.0"]
