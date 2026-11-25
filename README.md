# gphoto

Copy camera photos to the NAS. About 4 hours later they are in Google Photos, shrunk by Google, on the day they were taken.

## Why it works this way

- Google's public API stores full size only. Google shrinks photos for its own apps, so a real Chrome does the upload with "Back up folders".
- Google refuses to shrink a Nikon D7100 JPEG that carries an MPF block. Without the block, a 9.5 MB photo became 663 KB. The block holds a small preview of the same photo. It is removed from the copy that is sent.
- Phone photos are left alone. The phone sends its own, and its MPF block is an HDR gain map.
- The 4 hours are for deleting bad shots. They count from when the file lands on the NAS.

## Parts

| Container | Job | Can reach |
|---|---|---|
| `gphoto-incoming` | Finds photos, waits, strips a copy, puts it in `staging` | NAS read-only, no network |
| `gphoto-chrome` | Google Photos, signed in, watching `staging` | Internet, LAN desktop on port 3941 |
| `gphoto-google` | Checks Chrome, proves arrival, tidies `staging` | Chrome by a socket file, no network |
| `gphoto-web` | Status page | State read-only |

Each database has one writer: `incoming.db` and `google.db`, both in `state/`.

## How the NAS is watched

NFS does not report changes made by other machines, so it polls every 5 minutes. A folder is listed only if its modified time moved, or if a photo in it is waiting. Everything is listed once a day. Year folders before `SINCE` are skipped. A file's content is read only when it is due to go.

## What "In Google" means

Google Photos showed a photo at that capture second. A phone photo in the same second can stand in for it. Staged copies are removed 30 days after that, and only while nothing is missing. NAS files are never changed.

## Set up

1. Copy `deploy/` to the Docker host. Copy `.env.example` to `.env` and fill it in. Set `SOURCE` to this repo.
2. `mkdir -p config staging state control && docker compose up -d --build`
3. Open `https://LAN_ADDRESS:3941`. Sign in to Google Photos. Choose Storage saver in Settings.
4. Click **+**, **Back up folders**, and pick `/staging`.
5. Restart `gphoto-chrome`. Click **+**, **Folder backup**, **Update permissions**, **Allow on every visit**.

The status page needs Traefik and a Cloudflare Access application. The app checks the Access token itself, so going around Cloudflare is refused.

## Runbook

| Problem | Do |
|---|---|
| Anything odd, or after a host reboot | `docker compose up -d` |
| Signed out, or folder permission lost | Open Chrome on port 3941 and follow the status page |
| NAS check has not run | Check the NAS. A hard NFS mount waits for it, then carries on |
| Send one photo again | `docker compose run --rm gphoto-incoming python -m gphoto.incoming --root /photos --staging /staging --db /state/incoming.db --since 2000-01-01 --retry "2026/folder/DSC_1.JPG"` |
| Stop flagging a photo | The same with `--dismiss` |
| Back up | Stop all four. Copy `state/` and `config/gprofile/`. Restore them as a pair |
| `incoming.db` lost | Everything since `SINCE` is staged again with the same bytes. Google should match them, not tested |
| Update Chrome | Back up first. Chrome profiles do not go back a version. Change `CHROME_IMAGE`, then `docker compose up -d` |

## Develop

Needs Python 3.12 and exiftool.

```bash
pip install -r gphoto/requirements.txt pytest httpx
pytest
```
