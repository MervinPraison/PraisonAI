FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install flask praisonai==0.0.34 gunicorn markdown
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "api:app"]
