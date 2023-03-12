FROM python:3.11.2-slim
WORKDIR /wkk-bot
COPY requirements.txt requirements.txt
RUN apt-get update \
    && apt-get install libopus0 \
    && pip install -r requirements.txt
COPY . .
CMD ["python", "./src/main.py"]