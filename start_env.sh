#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "🚀 Booting up Enterprise SaaS Environment..."

# ==========================================
# CONFIGURATION
# ==========================================
# Base directories based on your Kali setup
PROJECT_ROOT="$HOME/new_folder"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/my-monorepo/apps/dashboards"

# Automatically grab your local Kali IP address (e.g., 192.168.x.x)
LOCAL_IP=$(hostname -I | awk '{print $1}')
TENANT_DOMAIN=${1:-$LOCAL_IP}

echo "🌐 Detected Local IP for Tenant Domain: $TENANT_DOMAIN"

# ==========================================
# 1. START INFRASTRUCTURE
# ==========================================
echo "🐳 Starting Docker containers (Postgres & Redis)..."
cd $BACKEND_DIR
sudo docker compose -f docker-compose.local.yml up -d

echo "⏳ Waiting 3 seconds for database engines to initialize..."
sleep 3

# ==========================================
# 2. BACKEND SETUP (Migrations & Tenant)
# ==========================================
echo "🐍 Running Django migrations..."
# Assuming you run this script while your (venv) is active
python manage.py migrate

echo "🏢 Verifying and updating 'web' tenant address to $TENANT_DOMAIN..."
python manage.py shell -c "
from core.models import Tenant
t, created = Tenant.objects.get_or_create(name='web', defaults={'domain': '$TENANT_DOMAIN', 'is_active': True})
t.domain = '$TENANT_DOMAIN'
t.save()
"

# ==========================================
# 3. LAUNCH SERVERS
# ==========================================
echo "🔥 Starting Django Backend on Port 8000..."
python manage.py runserver 0.0.0.0:8000 &
DJANGO_PID=$!

echo "⚛️  Starting React Frontend..."
cd $FRONTEND_DIR
npm run dev &
REACT_PID=$!

# ==========================================
# 4. GRACEFUL SHUTDOWN (The trap)
# ==========================================
# This function runs automatically when you press Ctrl+C
cleanup() {
    echo ""
    echo "🛑 Shutting down servers..."
    kill $DJANGO_PID 2>/dev/null || true
    kill $REACT_PID 2>/dev/null || true
    
    echo "🧹 Spinning down Docker containers..."
    cd $BACKEND_DIR
    sudo docker compose -f docker-compose.local.yml down
    
    echo "👋 Environment safely shut down. See you next time!"
    exit 0
}

# Trap the SIGINT signal (Ctrl+C) and route it to the cleanup function
trap cleanup SIGINT

# ==========================================
# 5. KEEP ALIVE
# ==========================================
echo "====================================================="
echo "✅ ENVIRONMENT IS LIVE!"
echo "📡 Backend API:  http://$TENANT_DOMAIN:8000"
echo "💻 React UI:     Check Vite output above (usually Port 5173)"
echo "⚠️  Press [Ctrl+C] to safely shut down the entire stack."
echo "====================================================="

# Wait for background processes to finish (keeps the script running)
wait
