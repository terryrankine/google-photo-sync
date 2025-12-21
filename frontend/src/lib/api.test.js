import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchJSON, postJSON, putJSON, deleteJSON, api } from './api.js';

describe('api module', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('fetchJSON', () => {
    it('fetches JSON from endpoint', async () => {
      const mockData = { status: 'ok' };
      global.fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockData)
      });

      const result = await fetchJSON('/api/status');

      expect(global.fetch).toHaveBeenCalledWith('/api/status');
      expect(result).toEqual(mockData);
    });

    it('throws on non-ok response', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 404
      });

      await expect(fetchJSON('/api/notfound')).rejects.toThrow('API error: 404');
    });

    it('throws on 500 error', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 500
      });

      await expect(fetchJSON('/api/broken')).rejects.toThrow('API error: 500');
    });
  });

  describe('postJSON', () => {
    it('posts JSON data', async () => {
      const mockData = { id: 1 };
      global.fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockData)
      });

      const result = await postJSON('/api/jobs', { type: 'sync' });

      expect(global.fetch).toHaveBeenCalledWith('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'sync' })
      });
      expect(result).toEqual(mockData);
    });

    it('posts empty object by default', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({})
      });

      await postJSON('/api/jobs');

      expect(global.fetch).toHaveBeenCalledWith('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
      });
    });

    it('throws on error response', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 400
      });

      await expect(postJSON('/api/jobs')).rejects.toThrow('API error: 400');
    });
  });

  describe('putJSON', () => {
    it('puts JSON data', async () => {
      const mockData = { updated: true };
      global.fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockData)
      });

      const result = await putJSON('/api/config', { theme: 'dark' });

      expect(global.fetch).toHaveBeenCalledWith('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: 'dark' })
      });
      expect(result).toEqual(mockData);
    });
  });

  describe('deleteJSON', () => {
    it('deletes resource', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ deleted: true })
      });

      const result = await deleteJSON('/api/jobs/123');

      expect(global.fetch).toHaveBeenCalledWith('/api/jobs/123', {
        method: 'DELETE'
      });
      expect(result).toEqual({ deleted: true });
    });
  });

  describe('api object', () => {
    beforeEach(() => {
      global.fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({})
      });
    });

    describe('dashboard endpoints', () => {
      it('getDashboard calls correct endpoint', async () => {
        await api.getDashboard();
        expect(global.fetch).toHaveBeenCalledWith('/api/dashboard');
      });

      it('getStatus calls correct endpoint', async () => {
        await api.getStatus();
        expect(global.fetch).toHaveBeenCalledWith('/api/status');
      });
    });

    describe('job endpoints', () => {
      it('getJobs calls with default limit', async () => {
        await api.getJobs();
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs?limit=20');
      });

      it('getJobs calls with custom limit', async () => {
        await api.getJobs(50);
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs?limit=50');
      });

      it('getActiveJob calls correct endpoint', async () => {
        await api.getActiveJob();
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs/active');
      });

      it('startJob posts to jobs endpoint', async () => {
        await api.startJob();
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs', expect.objectContaining({
          method: 'POST'
        }));
      });

      it('pauseJob posts to pause endpoint', async () => {
        await api.pauseJob(123);
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs/123/pause', expect.objectContaining({
          method: 'POST'
        }));
      });

      it('resumeJob posts to resume endpoint', async () => {
        await api.resumeJob(123);
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs/123/resume', expect.objectContaining({
          method: 'POST'
        }));
      });

      it('cancelJob posts to cancel endpoint', async () => {
        await api.cancelJob(123);
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs/123/cancel', expect.objectContaining({
          method: 'POST'
        }));
      });

      it('deleteJob deletes job', async () => {
        await api.deleteJob(123);
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs/123', expect.objectContaining({
          method: 'DELETE'
        }));
      });

      it('cleanupJobs calls with default params', async () => {
        await api.cleanupJobs();
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs/cleanup?days=7&status=all', expect.objectContaining({
          method: 'DELETE'
        }));
      });

      it('cleanupJobs calls with custom params', async () => {
        await api.cleanupJobs(0, 'completed');
        expect(global.fetch).toHaveBeenCalledWith('/api/jobs/cleanup?days=0&status=completed', expect.objectContaining({
          method: 'DELETE'
        }));
      });
    });

    describe('stats endpoints', () => {
      it('getStats calls correct endpoint', async () => {
        await api.getStats();
        expect(global.fetch).toHaveBeenCalledWith('/api/stats/cards');
      });

      it('getChartData calls correct endpoint', async () => {
        await api.getChartData();
        expect(global.fetch).toHaveBeenCalledWith('/api/stats/chart');
      });

      it('getDailyStats calls correct endpoint', async () => {
        await api.getDailyStats();
        expect(global.fetch).toHaveBeenCalledWith('/api/stats/daily');
      });

      it('getRecentUploads calls with default params', async () => {
        await api.getRecentUploads();
        expect(global.fetch).toHaveBeenCalledWith('/api/uploads/recent?minutes=5&limit=20');
      });

      it('getRecentUploads calls with custom params', async () => {
        await api.getRecentUploads(10, 50);
        expect(global.fetch).toHaveBeenCalledWith('/api/uploads/recent?minutes=10&limit=50');
      });

      it('backfillStats posts to backfill endpoint', async () => {
        await api.backfillStats();
        expect(global.fetch).toHaveBeenCalledWith('/api/stats/backfill', expect.objectContaining({
          method: 'POST'
        }));
      });
    });

    describe('logs endpoints', () => {
      it('getLogs calls with default limit', async () => {
        await api.getLogs();
        expect(global.fetch).toHaveBeenCalledWith('/api/logs?limit=100');
      });

      it('getLogs calls with custom limit', async () => {
        await api.getLogs(50);
        expect(global.fetch).toHaveBeenCalledWith('/api/logs?limit=50');
      });

      it('getLogs filters by level', async () => {
        await api.getLogs(100, 'ERROR');
        expect(global.fetch).toHaveBeenCalledWith('/api/logs?limit=100&level=ERROR');
      });
    });

    describe('files endpoints', () => {
      it('getFiles calls with default params', async () => {
        await api.getFiles();
        expect(global.fetch).toHaveBeenCalledWith('/api/files?page=1&limit=50');
      });

      it('getFiles calls with pagination', async () => {
        await api.getFiles(2, 100);
        expect(global.fetch).toHaveBeenCalledWith('/api/files?page=2&limit=100');
      });

      it('getFiles calls with search filter', async () => {
        await api.getFiles(1, 50, 'photo.jpg');
        expect(global.fetch).toHaveBeenCalledWith('/api/files?page=1&limit=50&search=photo.jpg');
      });

      it('getFiles calls with status filter', async () => {
        await api.getFiles(1, 50, '', 'uploaded');
        expect(global.fetch).toHaveBeenCalledWith('/api/files?page=1&limit=50&status=uploaded');
      });

      it('getFiles calls with sorting', async () => {
        await api.getFiles(1, 50, '', '', 'mtime', 'desc');
        expect(global.fetch).toHaveBeenCalledWith('/api/files?page=1&limit=50&sort_by=mtime&sort_dir=desc');
      });

      it('getFiles encodes special characters in search', async () => {
        await api.getFiles(1, 50, 'photo & video.jpg');
        expect(global.fetch).toHaveBeenCalledWith('/api/files?page=1&limit=50&search=photo%20%26%20video.jpg');
      });
    });

    describe('config endpoints', () => {
      it('getConfig calls correct endpoint', async () => {
        await api.getConfig();
        expect(global.fetch).toHaveBeenCalledWith('/api/config');
      });

      it('updateConfig puts config', async () => {
        await api.updateConfig({ theme: 'dark' });
        expect(global.fetch).toHaveBeenCalledWith('/api/config', expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ theme: 'dark' })
        }));
      });

      it('updateSourceDirs puts source dirs', async () => {
        await api.updateSourceDirs(['/photos', '/videos']);
        expect(global.fetch).toHaveBeenCalledWith('/api/config/source-dirs', expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ dirs: ['/photos', '/videos'] })
        }));
      });
    });

    describe('live metrics', () => {
      it('getLiveMetrics calls correct endpoint', async () => {
        await api.getLiveMetrics();
        expect(global.fetch).toHaveBeenCalledWith('/api/workers/live');
      });
    });
  });
});
