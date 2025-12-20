# Bug Tracker

## Fixed Bugs

### BUG-001: Deduplication detection not working [FIXED]
- **Severity**: Low
- **Description**: `was_deduplicated` flag not set when Google Photos deduplicates
- **File**: `src/uploader.py:_create_media_item()`
- **Fix**: Added `known_media_ids` tracking to detect when Google returns an existing media_id

### BUG-002: Statistics page missing Overview section [FIXED]
- **Severity**: Medium
- **File**: `frontend/src/lib/pages/Stats.svelte`
- **Fix**: Added Overview section with Total Files, Uploaded, Unique Hashes, and Total Size stats

### BUG-003: Files page missing search/filter controls [FIXED]
- **Severity**: Medium
- **File**: `frontend/src/lib/pages/Files.svelte`
- **Fix**: Added search input and status filter dropdown with All/Pending/Uploaded/Error options

### BUG-005: Old failed batches clutter batch history [FIXED]
- **Severity**: Low
- **Fix**: Added `DELETE /api/batches/cleanup` and `DELETE /api/batches/{batch_id}` endpoints

### BUG-004: Visual regression tests need baseline snapshots [FIXED]
- **Severity**: Low
- **Fix**: Generated baseline screenshots with `npx playwright test --update-snapshots`
- Also fixed test selectors for more robust element matching

## Open Bugs

(None)

## Notes

Additional fixes made:
- Fixed settings page field name mismatch (Config.svelte now correctly maps to API field names)
- Added `PUT /api/config/source-dirs` endpoint for updating source directories
- Fixed unit tests to match current database schema (added required foreign key setup)
- Added commits to task_queue.py database operations
