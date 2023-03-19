FROM python:3.11.2-slim
WORKDIR /wkk-bot
CMD ["python", "./src/main.py"]
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN apt-get update \
    && apt-get -y install libopus0 --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY . .
