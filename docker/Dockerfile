FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create praison config directory
RUN mkdir -p /root/.praison

# Install Python packages (using latest versions)
RUN pip install --no-cache-dir \
    flask \
    "praisonai>=2.3.24" \
    "praisonai[api]" \
    gunicorn \
    markdown

# Copy application code
COPY . .

# Set environment variables for directory management
ENV PRAISON_CONFIG_DIR=/root/.praison
ENV DOCKER_CONTAINER=true

# Create health check API if api.py doesn't exist
RUN if [ ! -f api.py ]; then \
    echo "from flask import Flask\n\
app = Flask(__name__)\n\
\n\
@app.route('/health')\n\
def health():\n\
    return {'status': 'healthy'}, 200\n\
\n\
if __name__ == '__main__':\n\
    app.run()" > api.py; \
fi

EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "api:app"]
