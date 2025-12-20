# Task List

## Completed

- [x] Set up Svelte + Vite frontend in `frontend/`
- [x] Create Dashboard component with stats cards
- [x] Add Chart.js for graphs
- [x] Create Batches, Stats, Files, Config pages
- [x] Update FastAPI to serve Svelte build from `web/static/`
- [x] Update Dockerfile with multi-stage build (Node + Python)
- [x] Implement token refresh in `src/auth.py` (TokenManager class)
- [x] Test real upload to Google Photos - PASSED
- [x] Create Playwright UI tests in `frontend/tests/ui.spec.js`
- [x] Fix timezone to Australia/Perth
- [x] Wire SyncOrchestrator to API endpoint
- [x] Fix schema column mismatches (filepath→local_path, total_bytes→bytes_hashed)
- [x] Test sync pipeline with 3 photos - PASSED (scan/hash/upload working)
- [x] Add /api/files endpoint for Files page
- [x] Fix SQL injection risk (removed dynamic SQL in _update_batch_progress)
- [x] Fix completed_at not being set on batch completion
- [x] Install context7 MCP for documentation lookup

## In Progress

- [ ] Add NAS mount solution for Docker Desktop
  - Network drives (Y:\) can't be mounted directly in Docker Desktop
  - Options: SMB inside container, run on NAS, or copy locally
  - Currently using `./test_photos` for local testing

## Blocked

- [ ] Fix failing Playwright tests (12 of 64 failing)
  - Statistics page needs Overview heading
  - Files page needs search/filter controls
  - Visual regression needs baseline snapshots

## Pending

- [ ] Add directory browser API endpoint (`GET /api/browse?path=`)
- [ ] Add directory browser UI component to Settings page
- [ ] Clean up old failed batch records from database
- [ ] Fix deduplication detection (BUG-001)

## Future Enhancements

- [ ] Add file upload progress tracking in UI
- [ ] Add websocket for real-time batch updates
- [ ] Add bulk retry for failed uploads
- [ ] Add export/import of database
- [ ] Add album support for organizing uploads

---

## Notes

### Docker Mount Configuration
The Y: drive (mapped to `\\rannas\photo`) cannot be mounted in Docker Desktop on Windows.
For testing, photos are copied to `./test_photos` which is mounted at `/photos`.
For production, run the container directly on the NAS.

### Testing Commands
```bash
# Run real upload test
python scripts/test_real_upload.py

# Run Playwright UI tests
cd frontend && npm test

# Run with headed browser
cd frontend && npm run test:headed

# Update visual snapshots
cd frontend && npx playwright test --update-snapshots
```

### Build Commands
```bash
# Build frontend
cd frontend && npm run build

# Rebuild Docker
docker-compose -f docker-compose.windows.yml build

# Restart container
docker-compose -f docker-compose.windows.yml down && docker-compose -f docker-compose.windows.yml up -d

# Access UI
http://localhost:18080
```

### API Endpoints
- `GET /api/status` - System status
- `GET /api/stats/cards` - Dashboard stats
- `GET /api/files` - List files with pagination
- `GET /api/batches` - List batch history
- `GET /api/batches/active` - Current running batch
- `POST /api/batches` - Start new sync
- `GET /api/config` - Get configuration
- `PUT /api/config` - Update configuration
- `POST /api/config/source-dirs` - Add source directory
