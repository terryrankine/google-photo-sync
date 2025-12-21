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

# Get build info
BUILD_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BUILD_VERSION="1.0.0-${BUILD_COMMIT}"

echo "Build info: $BUILD_VERSION ($BUILD_COMMIT) at $BUILD_TIME"
echo "Rebuilding container (with layer caching)..."

# Build with version info - uses layer caching for faster builds
$SSH_CMD "$NAS_HOST" "cd $NAS_PATH && \
    /usr/local/bin/docker-compose build \
        --build-arg BUILD_VERSION=$BUILD_VERSION \
        --build-arg BUILD_COMMIT=$BUILD_COMMIT \
        --build-arg BUILD_TIME=$BUILD_TIME && \
    /usr/local/bin/docker-compose up -d"

echo "Done."
