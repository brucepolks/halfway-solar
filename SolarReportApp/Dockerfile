FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir
RUN playwright install chromium --with-deps

COPY . .

RUN mkdir -p database reports uploads static debug_screenshots

EXPOSE 5050

CMD gunicorn --bind 0.0.0.0:$PORT --timeout 120 --workers 1 app:app
