FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip3 install -r requirements.txt

COPY . .
RUN mkdir -p /app/static/images && chmod -R 755 /app/static

EXPOSE 3000

CMD [ "python", "app.py"]