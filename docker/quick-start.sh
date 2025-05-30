#!/bin/bash

# PraisonAI Docker Quick Start Script
# This script helps users quickly get started with PraisonAI using Docker

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first:"
        echo "  - Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not available. Please install Docker Compose:"
        echo "  - Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    print_success "Docker and Docker Compose are available"
}

# Check if .env file exists, create from template if not
setup_environment() {
    if [ ! -f ".env" ]; then
        print_status "Creating .env file from template..."
        if [ -f ".env.template" ]; then
            cp .env.template .env
        else
            cat > .env << EOF
# PraisonAI Docker Environment Configuration
OPENAI_API_KEY=your_openai_api_key_here
CHAINLIT_AUTH_SECRET=$(openssl rand -hex 32 2>/dev/null || echo "your_chainlit_secret_here")
FLASK_ENV=development
CHAINLIT_HOST=0.0.0.0
UI_PORT=8082
CHAT_PORT=8083
API_PORT=8080
EOF
        fi
        print_warning "Please edit .env file and add your API keys before continuing"
        print_status "Required: OPENAI_API_KEY"
        read -p "Press Enter to continue after updating .env file..."
    else
        print_success ".env file already exists"
    fi
}

# Function to show menu
show_menu() {
    echo ""
    echo "=== PraisonAI Docker Quick Start ==="
    echo ""
    echo "1) Start UI Service (Web Interface) - Port 8082"
    echo "2) Start Chat Service - Port 8083"
    echo "3) Start API Service - Port 8080"
    echo "4) Start All Services (Recommended)"
    echo "5) Start Development Environment"
    echo "6) View Service Status"
    echo "7) View Logs"
    echo "8) Stop All Services"
    echo "9) Pull Latest Images"
    echo "10) Clean Up (Remove containers and volumes)"
    echo "11) Show Service URLs"
    echo "0) Exit"
    echo ""
}

# Start specific service
start_service() {
    local service=$1
    print_status "Starting $service service..."
    docker-compose up -d $service
    print_success "$service service started"
}

# Start all services
start_all_services() {
    print_status "Starting all PraisonAI services..."
    docker-compose up -d
    print_success "All services started"
    show_service_urls
}

# Start development environment
start_dev_environment() {
    print_status "Starting development environment..."
    if [ -f "docker-compose.dev.yml" ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d ui-dev chat-dev api-dev
        print_success "Development environment started"
        echo ""
        echo "Development services available:"
        echo "  - UI (with hot reload): http://localhost:${UI_PORT:-8082}"
        echo "  - Chat (with hot reload): http://localhost:${CHAT_PORT:-8083}"
        echo "  - API (with hot reload): http://localhost:${API_PORT:-8080}"
        echo "  - Jupyter Lab: http://localhost:8888"
        echo ""
    else
        print_warning "Development configuration not found, starting regular services"
        start_all_services
    fi
}

# Show service status
show_status() {
    print_status "Service Status:"
    docker-compose ps
}

# Show logs
show_logs() {
    echo ""
    echo "Which service logs would you like to view?"
    echo "1) All services"
    echo "2) UI service"
    echo "3) Chat service"
    echo "4) API service"
    echo "5) Agents service"
    read -p "Enter choice (1-5): " log_choice
    
    case $log_choice in
        1) docker-compose logs -f ;;
        2) docker-compose logs -f ui ;;
        3) docker-compose logs -f chat ;;
        4) docker-compose logs -f api ;;
        5) docker-compose logs -f agents ;;
        *) print_error "Invalid choice" ;;
    esac
}

# Stop all services
stop_services() {
    print_status "Stopping all services..."
    docker-compose down
    print_success "All services stopped"
}

# Pull latest images
pull_images() {
    print_status "Pulling latest images..."
    docker-compose pull
    print_success "Images updated"
}

# Clean up
cleanup() {
    print_warning "This will remove all containers, networks, and volumes"
    read -p "Are you sure? (y/N): " confirm
    if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
        print_status "Cleaning up..."
        docker-compose down -v --remove-orphans
        docker system prune -f
        print_success "Cleanup completed"
    fi
}

# Show service URLs
show_service_urls() {
    local ui_port=${UI_PORT:-8082}
    local chat_port=${CHAT_PORT:-8083}
    local api_port=${API_PORT:-8080}
    
    echo ""
    echo "=== Service URLs ==="
    echo "UI Service: http://localhost:$ui_port"
    echo "Chat Service: http://localhost:$chat_port"
    echo "API Service: http://localhost:$api_port"
    echo "API Health: http://localhost:$api_port/health"
    echo ""
}

# Check system requirements
check_requirements() {
    print_status "Checking system requirements..."
    
    # Check available memory
    if command -v free &> /dev/null; then
        available_ram=$(free -m | awk 'NR==2{printf "%.1f", $7/1024}')
        print_status "Available RAM: ${available_ram}GB"
        if (( $(echo "$available_ram < 2.0" | bc -l 2>/dev/null || echo "1") )); then
            print_warning "Low available memory. Recommended: 2GB+ available RAM"
        fi
    fi
    
    # Check disk space
    if command -v df &> /dev/null; then
        available_space=$(df -BG . | awk 'NR==2{print $4}' | sed 's/G//')
        print_status "Available disk space: ${available_space}GB"
        if [ "$available_space" -lt 5 ]; then
            print_warning "Low disk space. Recommended: 5GB+ available space"
        fi
    fi
}

# Main function
main() {
    clear
    echo "🤖 Welcome to PraisonAI Docker Setup!"
    echo ""
    
    # Check prerequisites
    check_docker
    check_requirements
    setup_environment
    
    # Main loop
    while true; do
        show_menu
        read -p "Enter your choice (0-11): " choice
        
        case $choice in
            1)
                start_service "ui"
                echo "UI Service: http://localhost:${UI_PORT:-8082}"
                ;;
            2)
                start_service "chat"
                echo "Chat Service: http://localhost:${CHAT_PORT:-8083}"
                ;;
            3)
                start_service "api"
                echo "API Service: http://localhost:${API_PORT:-8080}"
                ;;
            4)
                start_all_services
                ;;
            5)
                start_dev_environment
                ;;
            6)
                show_status
                ;;
            7)
                show_logs
                ;;
            8)
                stop_services
                ;;
            9)
                pull_images
                ;;
            10)
                cleanup
                ;;
            11)
                show_service_urls
                ;;
            0)
                print_success "Thank you for using PraisonAI!"
                exit 0
                ;;
            *)
                print_error "Invalid choice. Please try again."
                ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..."
    done
}

# Run main function
main