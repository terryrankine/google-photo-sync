# Google Photos Sync - Quickstart Guide

A NAS-native tool to sync your photo library to Google Photos with intelligent duplicate detection.

## Prerequisites

- Docker and Docker Compose
- A Google account
- Photos stored on a NAS or local filesystem

---

## Step 1: Google Cloud Setup

### 1.1 Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it something like `gphoto-sync`
4. Click **Create**

### 1.2 Enable the Photos Library API

1. In your new project, go to **APIs & Services** → **Library**
2. Search for `Photos Library API`
3. Click on it and press **Enable**

### 1.3 Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** (unless you have a Workspace account)
3. Fill in the required fields:
   - **App name**: `GPhoto Sync` (or any name)
   - **User support email**: your email
   - **Developer contact**: your email
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes**
6. Add these scopes:
   - `https://www.googleapis.com/auth/photoslibrary.appendonly` (upload photos)
   - `https://www.googleapis.com/auth/photoslibrary.readonly` (read library metadata)
7. Click **Save and Continue**
8. On **Test users**, add your Google account email
9. Click **Save and Continue**

> **Note**: While in "Testing" mode, tokens expire after 7 days. For production use, submit your app for verification.

### 1.4 Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Select **Desktop app** as the application type
4. Name it `GPhoto Sync Desktop`
5. Click **Create**
6. Click **Download JSON**
7. Rename the downloaded file to `client_id.json`

---

## Step 2: Directory Structure

Create the following directory structure:

```
gphoto-sync/
├── docker-compose.yml
├── config/
│   └── client_id.json    # Your OAuth credentials (from Step 1.4)
├── data/
│   └── (database will be created here)
└── photos/               # Mount point for your photos
```

### On Synology NAS

```bash
mkdir -p /volume1/docker/gphoto-sync/{config,data}
# Copy client_id.json to /volume1/docker/gphoto-sync/config/
```

### On Windows (for testing)

```powershell
mkdir gphoto-sync\config
mkdir gphoto-sync\data
mkdir gphoto-sync\test_photos
# Copy client_id.json to gphoto-sync\config\
```

---

## Step 3: Docker Compose Configuration

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  gphoto-sync:
    build: .
    # Or use: image: ghcr.io/terryrankine/gphoto-sync:latest
    ports:
      - "18080:8080"
    volumes:
      # OAuth credentials and token storage
      - ./config:/config

      # SQLite database storage
      - ./data:/data

      # Your photo directories (read-only recommended)
      - /volume1/photos:/photos:ro

      # Multiple sources example:
      # - /volume1/photos:/photos:ro
      # - /volume1/media/photos:/media:ro
    environment:
      - TZ=Australia/Perth  # Your timezone
      - LOG_LEVEL=INFO
    restart: unless-stopped
```

### Volume Mount Examples

| Use Case | Mount |
|----------|-------|
| Synology NAS | `/volume1/photos:/photos:ro` |
| Windows test | `./test_photos:/photos:ro` |
| Multiple dirs | Mount each, configure in Settings |

---

## Step 4: First Run & Authentication

### 4.1 Start the Container

```bash
cd /path/to/gphoto-sync
docker-compose up -d
```

### 4.2 Check Logs for Auth URL

```bash
docker-compose logs -f
```

Look for a message like:
```
Please visit this URL to authorize: https://accounts.google.com/o/oauth2/v2/auth?...
```

### 4.3 Complete Authentication

1. Copy the entire URL from the logs
2. Open it in a browser on any device
3. Sign in with your Google account
4. Grant the requested permissions
5. You'll be redirected to `localhost` - this is expected to fail
6. Copy the **entire URL** from your browser's address bar (including the `code=` parameter)
7. The app will detect the code and complete authentication

> **Tip**: If running on a headless NAS, paste the auth URL into a browser on your laptop/phone.

### 4.4 Verify Authentication

Check the logs for:
```
Token saved successfully
```

Or visit the web UI at `http://your-nas-ip:18080`

---

## Step 5: Configure Source Directories

1. Open the web UI: `http://your-nas-ip:18080`
2. Go to **Settings**
3. Set **Source Directories** (one per line):
   ```
   /photos
   /media
   ```
4. Adjust **File Extensions** if needed (default: `.jpg,.jpeg,.png,.heic,.mp4,.mov`)
5. Set **Ignore Patterns** for directories to skip (default: `.thumbnails,@eaDir`)
6. Click **Save Settings**

---

## Step 6: Start Syncing

1. Go to **Dashboard**
2. Click **Start Sync**
3. Watch the progress:
   - **Scan**: Discovers files on disk
   - **Hash**: Computes SHA256 for deduplication
   - **Upload**: Sends unique files to Google Photos

---

## Troubleshooting

### "Token expired" errors

Tokens in testing mode expire after 7 days. Re-authenticate:
```bash
docker-compose exec gphoto-sync rm /config/token.json
docker-compose restart gphoto-sync
# Follow auth flow again in logs
```

### "Permission denied" on photos

Ensure the container can read your photos:
```bash
# Check permissions
ls -la /volume1/photos

# On Synology, the container runs as root by default
# If using user namespaces, adjust accordingly
```

### Network drives on Windows

Docker Desktop cannot mount Windows network drives (like `Y:\`). Options:
1. Run the container directly on the NAS
2. Use a local test directory
3. Use WSL2 with network mount

### Container can't reach Google

Check DNS and network:
```bash
docker-compose exec gphoto-sync ping google.com
docker-compose exec gphoto-sync curl -I https://photoslibrary.googleapis.com
```

---

## How It Works

### Three-Phase Sync

1. **SCAN** (~50k files/sec): Fast filesystem traversal, skips unchanged files
2. **HASH** (~500 MB/sec): Parallel SHA256 computation for deduplication
3. **UPLOAD** (rate-limited): Google Photos API with retry logic

### Duplicate Detection

- Local: SHA256 hash comparison before upload
- Remote: Google Photos server-side deduplication (photos only, not videos)

### Data Storage

- `data/gphoto_sync.db`: SQLite database tracking all files
- `config/token.json`: OAuth refresh token (keep secure!)
- `config/client_id.json`: Your OAuth credentials

---

## API Limitations

Google Photos API has some important constraints:

| Feature | Limitation |
|---------|------------|
| Upload quality | **Original only** - no "Storage Saver" via API |
| Library access | Can only see items uploaded by this app |
| Deduplication | Photos: server-side dedup. Videos: none |
| Rate limits | ~10,000 uploads/day (varies) |

---

## Useful Commands

```bash
# View logs
docker-compose logs -f

# Restart container
docker-compose restart

# Rebuild after code changes
docker-compose build --no-cache && docker-compose up -d

# Database backup
docker-compose exec gphoto-sync sqlite3 /data/gphoto_sync.db ".backup /data/backup.db"

# Check container status
docker-compose ps
```

---

## Support

- GitHub Issues: [github.com/terryrankine/google-photo-sync/issues](https://github.com/terryrankine/google-photo-sync/issues)
