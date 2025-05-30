# PraisonAI Docker Setup

This directory contains Docker configurations for running PraisonAI services in containerized environments. The setup addresses directory management issues and provides comprehensive multi-service deployment options.

## 🐳 Available Services

### Core Services
- **UI Service** (`port 8082`) - Chainlit-based web interface
- **Chat Service** (`port 8083`) - Dedicated chat interface  
- **API Service** (`port 8080`) - REST API endpoint
- **Agents Service** - Standalone PraisonAI Agents runtime

### Docker Files
- `Dockerfile` - Basic API service
- `Dockerfile.ui` - UI service with web interface
- `Dockerfile.chat` - Chat-focused service
- `Dockerfile.dev` - Development environment with tools
- `Dockerfile.praisonaiagents` - Standalone agents framework
- `docker-compose.yml` - Multi-service orchestration

## 🚀 Quick Start

### Single Service
```bash
# Run UI service
docker run -p 8082:8082 -e OPENAI_API_KEY=your_key ghcr.io/mervinpraison/praisonai:ui

# Run Chat service  
docker run -p 8083:8083 -e OPENAI_API_KEY=your_key ghcr.io/mervinpraison/praisonai:chat

# Run API service
docker run -p 8080:8080 -e OPENAI_API_KEY=your_key ghcr.io/mervinpraison/praisonai:api
```

### Multi-Service with Docker Compose
```bash
# Create environment file
cat > .env << EOF
OPENAI_API_KEY=your_openai_api_key_here
CHAINLIT_AUTH_SECRET=your_secret_here
EOF

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## 📁 Directory Management

### Problem Solved
The original issue was that files like `chainlit.md`, `.chainlit` directory, and `public` folder were cluttering the root directory.

### Solution Implemented
All PraisonAI configuration and runtime files are now stored in `~/.praison/`:

```bash
~/.praison/
├── database.sqlite      # Chainlit database
├── chainlit.md         # Chainlit configuration 
├── .chainlit/          # Chainlit runtime files
└── config/             # PraisonAI configuration
```

### Environment Variables
```bash
PRAISON_CONFIG_DIR=/root/.praison      # Main config directory
CHAINLIT_CONFIG_DIR=/root/.praison     # Chainlit config location
CHAINLIT_DB_DIR=/root/.praison         # Database location
```

## 🔧 Service Configuration

### UI Service (Port 8082)
```yaml
environment:
  - CHAINLIT_PORT=8082
  - CHAINLIT_HOST=0.0.0.0
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - CHAINLIT_AUTH_SECRET=${CHAINLIT_AUTH_SECRET}
```

### Chat Service (Port 8083)  
```yaml
environment:
  - CHAINLIT_PORT=8083
  - CHAINLIT_HOST=0.0.0.0
  - OPENAI_API_KEY=${OPENAI_API_KEY}
```

### API Service (Port 8080)
```yaml
environment:
  - OPENAI_API_KEY=${OPENAI_API_KEY}
```

## 🎯 Service Endpoints

| Service | Port | Endpoint | Description |
|---------|------|----------|-------------|
| UI | 8082 | http://localhost:8082 | Web interface |
| Chat | 8083 | http://localhost:8083 | Chat interface |
| API | 8080 | http://localhost:8080 | REST API |
| API Health | 8080 | http://localhost:8080/health | Health check |

## 🔍 Health Checks

All services include health checks:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:PORT"]
  interval: 10s
  timeout: 5s
  retries: 3
```

## 📦 Package Versions

All Docker images use consistent, up-to-date versions:
- PraisonAI: `>=2.2.22`
- PraisonAI Agents: `>=0.0.92`
- Python: `3.11-slim`

## 🔒 Security Features

- Non-root user execution where possible
- Minimal base image (python:3.11-slim)
- No unnecessary packages installed
- Environment variable-based configuration
- Volume mounting for persistent data

## 🛠 Development

### Development Environment
```bash
# Use development Dockerfile with additional tools
docker build -f Dockerfile.dev -t praisonai:dev .
docker run -it -v $(pwd):/app praisonai:dev bash
```

### Custom Configuration
```bash
# Mount custom config directory
docker run -v ~/.praison:/root/.praison praisonai:ui
```

## 📊 Monitoring

### Docker Compose Monitoring
```bash
# View service status
docker-compose ps

# View resource usage
docker-compose top

# View logs for specific service
docker-compose logs ui
docker-compose logs chat
docker-compose logs api
```

## 🚨 Troubleshooting

### Common Issues

1. **Port conflicts**
   ```bash
   # Check port usage
   netstat -tlnp | grep :8082
   
   # Use different ports
   docker run -p 9082:8082 praisonai:ui
   ```

2. **Environment variables not loading**
   ```bash
   # Verify .env file
   cat .env
   
   # Set variables directly
   docker run -e OPENAI_API_KEY=your_key praisonai:ui
   ```

3. **Permission issues**
   ```bash
   # Check volume permissions
   ls -la ~/.praison/
   
   # Fix permissions
   sudo chown -R $(id -u):$(id -g) ~/.praison/
   ```

4. **Service won't start**
   ```bash
   # Check logs
   docker-compose logs service_name
   
   # Restart service
   docker-compose restart service_name
   ```

## 🔄 Updates

### Pulling Latest Images
```bash
# Pull latest images
docker-compose pull

# Restart with new images
docker-compose up -d
```

### Version Pinning
To use specific versions, update the Dockerfile:
```dockerfile
RUN pip install "praisonai==2.2.22" "praisonaiagents==0.0.92"
```

## 🌐 Production Deployment

### Recommended Production Setup
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  ui:
    image: ghcr.io/mervinpraison/praisonai:ui
    restart: unless-stopped
    environment:
      - CHAINLIT_HOST=0.0.0.0
      - CHAINLIT_PORT=8082
    volumes:
      - praison_data:/root/.praison
    networks:
      - praison_network
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

### Load Balancer Configuration
For production environments, consider using nginx or similar:
```nginx
upstream praisonai {
    server localhost:8082;
    server localhost:8083;
}

server {
    listen 80;
    location / {
        proxy_pass http://praisonai;
    }
}
```

This Docker setup provides a clean, organized, and scalable way to deploy PraisonAI services while solving the directory management issues mentioned in the original request.