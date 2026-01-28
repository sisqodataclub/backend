#!/bin/bash

set -e

# ==========================================
# 🔧 CONFIGURATION
# ==========================================
REPO_URL="https://github.com/sisqodataclub/backend.git"
PROJECT_DIR="/opt/backend"
BACKUP_DIR="${PROJECT_DIR}/backups"
DOMAIN_NAME="core.franciscodes.com"  # ✅ Added: Defined here for easy changing
DATE=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting deployment for ${DOMAIN_NAME}...${NC}"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# 1. Ensure Docker Network Exists
echo -e "${BLUE}🌐 Checking Docker network...${NC}"
if ! docker network ls | grep -q "proxy_network"; then
    echo -e "${YELLOW}⚠️  Network 'proxy_network' not found. Creating it...${NC}"
    docker network create proxy_network
    echo -e "${GREEN}✅ Network created.${NC}"
else
    echo -e "${GREEN}✅ Network 'proxy_network' exists.${NC}"
fi

# 2. Clone or update repo
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${BLUE}📂 Cloning repository...${NC}"
    git clone "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
else
    echo -e "${BLUE}📂 Updating repository...${NC}"
    cd "$PROJECT_DIR"
    git fetch --all
    git reset --hard origin/main
    git clean -fd
fi

# 3. Validate .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ ERROR: .env file not found!${NC}"
    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}📝 Creating .env from .env.example...${NC}"
        cp .env.example .env
        echo -e "${YELLOW}✏️  Please edit .env file with your actual values and run again${NC}"
        echo -e "${YELLOW}   nano /opt/backend/.env${NC}"
        exit 1
    else
        echo -e "${RED}❌ .env.example not found!${NC}"
        exit 1
    fi
fi

# Load environment variables
echo -e "${BLUE}📄 Loading environment variables...${NC}"
source .env

# 4. Validate required environment variables
# ✅ Added DJANGO_ALLOWED_HOSTS to ensure domain is configured
REQUIRED_VARS=("DJANGO_SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "DB_HOST" "DJANGO_ALLOWED_HOSTS")
missing_vars=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo -e "${RED}❌ ERROR: Missing required environment variables:${NC}"
    for var in "${missing_vars[@]}"; do
        echo -e "   ${RED}• $var${NC}"
    done
    echo -e "${YELLOW}💡 Please set them in your .env file${NC}"
    exit 1
fi

# 5. Validate secret key is not default
if [[ "$DJANGO_SECRET_KEY" == "change-this-to-a-very-secure-random-key" ]]; then
    echo -e "${RED}❌ ERROR: You must change the DJANGO_SECRET_KEY in .env file${NC}"
    echo -e "${YELLOW}💡 Generate a new one:${NC}"
    echo -e "   python3 -c \"import secrets; print(secrets.token_urlsafe(50))\""
    exit 1
fi

echo -e "${GREEN}✅ All environment variables validated${NC}"

# 6. Backup database
echo -e "${BLUE}💾 Attempting database backup...${NC}"
if command -v pg_dump &> /dev/null && [ -n "$DB_HOST" ]; then
    BACKUP_FILE="${BACKUP_DIR}/db_backup_${DATE}.sql"
    if PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" > "$BACKUP_FILE" 2>/dev/null; then
        echo -e "${GREEN}✅ Database backup created: $(basename "$BACKUP_FILE")${NC}"
    else
        echo -e "${YELLOW}⚠️  Database backup skipped (connection failed or credentials invalid)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Database backup skipped (pg_dump not installed)${NC}"
fi

# 7. Build and Run
echo -e "${BLUE}🔧 Stopping existing containers...${NC}"
docker compose down --remove-orphans

echo -e "${BLUE}🛠️ Building new image...${NC}"
docker compose build --no-cache

echo -e "${BLUE}🔄 Running database migrations...${NC}"
docker compose run --rm backend python manage.py migrate --noinput

echo -e "${BLUE}📦 Collecting static files...${NC}"
docker compose run --rm backend python manage.py collectstatic --noinput

echo -e "${BLUE}🚀 Starting containers...${NC}"
docker compose up -d

# 8. Health Check
echo -e "${BLUE}⏳ Waiting for service to become healthy...${NC}"
for i in {1..30}; do
    if docker ps --filter "name=backend" --format "{{.Status}}" | grep -q "healthy"; then
        echo -e "${GREEN}✅ Service is healthy!${NC}"
        break
    elif [ $i -eq 30 ]; then
        echo -e "${RED}❌ Service did not become healthy in time${NC}"
        echo -e "${YELLOW}📋 Container logs:${NC}"
        docker logs backend --tail 50
        exit 1
    else
        echo -n "."
        sleep 2
    fi
done

echo -e "${BLUE}🏥 Testing health endpoint...${NC}"
if docker exec backend curl -s http://localhost:8000/health/ | grep -q "healthy"; then
    echo -e "${GREEN}✅ Health endpoint working${NC}"
else
    echo -e "${YELLOW}⚠️  Health endpoint check failed (Check docker logs)${NC}"
fi

# 9. Output Instructions
echo -e "${GREEN}🎉 Deployment complete!${NC}"
echo ""
echo -e "${BLUE}📋 Next steps in Nginx Proxy Manager:${NC}"
echo "1. Go to http://$(curl -s ifconfig.me):81"
echo "2. Click 'Proxy Hosts' → 'Add Proxy Host'"
echo "3. Configure:"
echo "   - Domain Names: ${DOMAIN_NAME}"
echo "   - Scheme: http"
echo "   - Forward Hostname: backend"
echo "   - Forward Port: 8000"
echo "4. SSL Tab: Request Let's Encrypt certificate"
echo ""
echo -e "${GREEN}🌐 Your site will be available at: https://${DOMAIN_NAME}${NC}"
echo ""
echo -e "${BLUE}🔧 Useful commands:${NC}"
echo "   View logs: ${GREEN}docker logs -f backend${NC}"
echo "   Check health: ${GREEN}curl http://localhost:8000/health/${NC}"
echo "   Create superuser: ${GREEN}docker exec -it backend python manage.py createsuperuser${NC}"
echo "   Shell access: ${GREEN}docker exec -it backend bash${NC}"
echo "   Create Tenant: ${GREEN}docker exec -it backend python manage.py create_tenant --name=demo --domain=demo.${DOMAIN_NAME}${NC}"