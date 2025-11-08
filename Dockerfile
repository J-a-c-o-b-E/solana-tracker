FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["python", "-u", "main.py"]
```

## 2. Make sure your requirements.txt has:
```
python-telegram-bot==20.7
aiohttp==3.9.1
