#!/bin/bash
# Deploy to NAS - excludes stateful directories to prevent data loss
#
# NEVER sync: data/, config/ - these contain production database and credentials

set -e

NAS_HOST="terry-linux@192.168.11.186"
NAS_PATH="/volume1/docker/gphoto-sync"

# Use Windows SSH if running in WSL (has the SSH keys)
if [[ -f /mnt/c/Windows/System32/OpenSSH/ssh.exe ]]; then
    SSH_CMD="/mnt/c/Windows/System32/OpenSSH/ssh.exe"
else
    SSH_CMD="ssh"
fi

# PRE-DEPLOY TESTS - fail fast before wasting time
echo "Running pre-deploy tests..."

# Test Python imports
if [[ -f .venv/bin/python ]]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

echo "  Checking Python imports..."
$PYTHON -c "from web.app import app; from web.api import router; print('    Python OK')" || {
    echo "ERROR: Python import failed. Fix before deploying."
    exit 1
}

# Test frontend build
echo "  Building frontend..."
(cd frontend && npm run build) || {
    echo "ERROR: Frontend build failed. Fix before deploying."
    exit 1
}

echo "Pre-deploy tests passed."
echo ""
echo "Deploying to NAS (excluding data/ and config/)..."

tar --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='frontend/node_modules' \
    --exclude='.venv' \
    --exclude='*.pyc' \
    --exclude='data' \
    --exclude='config' \
    --exclude='photos' \
    --exclude='test_photos' \
    --exclude='*.db' \
    --exclude='*.db-wal' \
    --exclude='*.db-shm' \
    -czf - . | $SSH_CMD "$NAS_HOST" "cd $NAS_PATH && tar -xzf -"

echo "Rebuilding container..."
$SSH_CMD "$NAS_HOST" "cd $NAS_PATH && /usr/local/bin/docker-compose build --no-cache && /usr/local/bin/docker-compose up -d"

echo "Done."
