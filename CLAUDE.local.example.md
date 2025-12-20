# Local Development Notes (copy to CLAUDE.local.md)

## NAS Deployment (Synology)

- **Host**: YOUR_NAS_IP
- **User**: YOUR_USERNAME (in docker group, no sudo needed)
- **Docker path**: /usr/local/bin/docker
- **Project path**: /volume1/docker/gphoto-sync
- **SSH/SCP**: Use `C:\Windows\System32\OpenSSH\ssh.exe` (Windows OpenSSH, not Git's)

### Deploy Commands

```powershell
# Copy file to NAS
powershell -Command "& 'C:\Windows\System32\OpenSSH\scp.exe' 'localfile' 'YOUR_USERNAME@YOUR_NAS_IP:/volume1/docker/gphoto-sync/path'"

# SSH to NAS
powershell -Command "& 'C:\Windows\System32\OpenSSH\ssh.exe' YOUR_USERNAME@YOUR_NAS_IP"

# Rebuild container
powershell -Command "& 'C:\Windows\System32\OpenSSH\ssh.exe' YOUR_USERNAME@YOUR_NAS_IP 'cd /volume1/docker/gphoto-sync && /usr/local/bin/docker-compose build --no-cache && /usr/local/bin/docker-compose up -d'"
```
