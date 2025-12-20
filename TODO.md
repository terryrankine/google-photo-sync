# Google Photos Sync - TODO

## Ready to Deploy

Files changed - need to copy to NAS:
- `src/uploader.py` - Added UploadTokenBatcher, batches up to 50 items per batchCreate call
- `src/sync.py` - Uses token batcher for batched uploads
- `src/task_queue.py` - Added batch_handlers param to BatchWorker
- `web/api.py` - Added `/api/files/{id}/preview` endpoint
- `frontend/src/lib/pages/Files.svelte` - Image/video preview modal
- `frontend/src/lib/pages/Jobs.svelte` - Delete job buttons, Clear Finished
- `frontend/src/lib/api.js` - Added deleteJob, cleanupJobs methods

### Deploy Commands (run from Windows PowerShell)

```powershell
cd C:\Users\terryr\code\google-photo-container

# Build frontend first
cd frontend && npm run build && cd ..

# Copy files to NAS
scp src/uploader.py src/sync.py src/task_queue.py web/api.py terry-linux@192.168.11.186:/volume1/docker/gphoto-sync/src/
scp -r web/static/* terry-linux@192.168.11.186:/volume1/docker/gphoto-sync/web/static/

# Rebuild container
ssh terry-linux@192.168.11.186 "cd /volume1/docker/gphoto-sync && /usr/local/bin/docker-compose up -d --build"
```

## Completed Features

### Dashboard UI Fixes
- [x] Fix layout when hash queue is empty (upload workers now full width)
- [x] Hide "Last 7 Days" chart when no data
- [x] Hide "Recent Activity" section when empty

### File Preview
- [x] API endpoint: `GET /api/files/{id}/preview` - serves image/video files
- [x] Frontend: Click any file row to open preview modal
- [x] Supports: jpg, jpeg, png, gif, webp, heic, heif, mp4, mov, avi, mkv
- [x] ESC key closes modal

### File Search
- [x] Already implemented in Files page
- [x] Search by filename, relative_path
- [x] API: `/api/files?search=query&status=filter`

### Job Management
- [x] Delete job button (trash icon) on each non-active job
- [x] "Clear Finished" button at top of Jobs page
- [x] API: `DELETE /api/jobs/{id}` and `DELETE /api/jobs/cleanup`

## Pending Features

### Statistics Page Review
- [ ] Review usefulness of statistics page
- [ ] Consider what metrics would be valuable

## Technical Debt

### WSL Interop Fix
WSL systemd may break Windows executable interop. To fix:

1. Add to `/etc/wsl.conf`:
```ini
[interop]
enabled=true
appendWindowsPath=true
```

2. Restart WSL: `wsl --shutdown` from PowerShell

### 1Password SSH in WSL
Once interop is fixed, use Windows SSH directly:
```bash
git config --global core.sshCommand ssh.exe
alias ssh='ssh.exe'
alias ssh-add='ssh-add.exe'
```
