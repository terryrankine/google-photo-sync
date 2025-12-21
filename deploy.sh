#!/bin/bash
# Deploy to NAS - excludes stateful directories to prevent data loss
#
# NEVER sync: data/, config/ - these contain production database and credentials

set -e

NAS_HOST="terry-linux@192.168.11.186"
NAS_PATH="/volume1/docker/gphoto-sync"

echo "Deploying to NAS (excluding data/ and config/)..."

tar --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='frontend/node_modules' \
    --exclude='*.pyc' \
    --exclude='data' \
    --exclude='config' \
    --exclude='photos' \
    --exclude='test_photos' \
    --exclude='*.db' \
    --exclude='*.db-wal' \
    --exclude='*.db-shm' \
    -czf - . | ssh "$NAS_HOST" "cd $NAS_PATH && tar -xzf -"

echo "Rebuilding container..."
ssh "$NAS_HOST" "cd $NAS_PATH && /usr/local/bin/docker-compose build --no-cache && /usr/local/bin/docker-compose up -d"

echo "Done."
