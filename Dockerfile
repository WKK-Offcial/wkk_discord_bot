FROM python:3.11.2-slim
WORKDIR /wkk-bot
CMD ["python", "./src/main.py"]
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get update \
    && apt-get -y install --no-install-recommends libopus0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY . .
