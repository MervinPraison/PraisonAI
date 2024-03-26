FROM python:3.11-slim
WORKDIR /app
# Copy only api.py and agents.yaml to /app in the container
COPY api.py agents.yaml ./
RUN pip install flask praisonai==0.0.15 gunicorn markdown
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "api:app"]