import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import {
  stats, dailyStats, chartData, recentUploads, statsLoaded,
  loadAllStats, refreshChart, refreshRecentUploads
} from './stats.js';

// Mock the api module
vi.mock('../api.js', () => ({
  api: {
    getStats: vi.fn(),
    getDailyStats: vi.fn(),
    getChartData: vi.fn(),
    getRecentUploads: vi.fn()
  }
}));

import { api } from '../api.js';

describe('stats store', () => {
  beforeEach(() => {
    // Reset stores to initial state
    stats.set({ total_files: 0, uploaded_files: 0, unique_hashes: 0, total_bytes: 0 });
    dailyStats.set([]);
    chartData.set({ labels: [], datasets: [] });
    recentUploads.set({ count: 0, total_bytes: 0, uploads: [] });
    statsLoaded.set(false);

    // Reset mocks
    vi.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have empty initial stats', () => {
      expect(get(stats)).toEqual({
        total_files: 0,
        uploaded_files: 0,
        unique_hashes: 0,
        total_bytes: 0
      });
    });

    it('should have statsLoaded as false initially', () => {
      expect(get(statsLoaded)).toBe(false);
    });

    it('should have empty chart data initially', () => {
      expect(get(chartData)).toEqual({ labels: [], datasets: [] });
    });
  });

  describe('loadAllStats', () => {
    it('should load all stats and set statsLoaded to true', async () => {
      const mockStats = { total_files: 100, uploaded_files: 50, unique_hashes: 90, total_bytes: 1000000 };
      const mockDaily = [{ date: '2025-12-21', files_uploaded: 10 }];
      const mockChart = { labels: ['12:00'], uploaded: [5], hashed: [10], errors: [0] };
      const mockRecent = { count: 3, total_bytes: 5000, uploads: [] };

      api.getStats.mockResolvedValue(mockStats);
      api.getDailyStats.mockResolvedValue(mockDaily);
      api.getChartData.mockResolvedValue(mockChart);
      api.getRecentUploads.mockResolvedValue(mockRecent);

      await loadAllStats();

      expect(get(stats)).toEqual(mockStats);
      expect(get(dailyStats)).toEqual(mockDaily);
      expect(get(recentUploads)).toEqual(mockRecent);
      expect(get(statsLoaded)).toBe(true);
    });

    it('should format chart data with correct datasets', async () => {
      const mockChart = { labels: ['12:00', '12:05'], uploaded: [5, 8], hashed: [10, 15], errors: [0, 1] };

      api.getStats.mockResolvedValue({});
      api.getDailyStats.mockResolvedValue([]);
      api.getChartData.mockResolvedValue(mockChart);
      api.getRecentUploads.mockResolvedValue({ count: 0, total_bytes: 0, uploads: [] });

      await loadAllStats();

      const chart = get(chartData);
      expect(chart.labels).toEqual(['12:00', '12:05']);
      expect(chart.datasets).toHaveLength(3);
      expect(chart.datasets[0].label).toBe('Uploaded');
      expect(chart.datasets[0].data).toEqual([5, 8]);
      expect(chart.datasets[1].label).toBe('Hashed');
      expect(chart.datasets[1].data).toEqual([10, 15]);
      expect(chart.datasets[2].label).toBe('Errors');
      expect(chart.datasets[2].data).toEqual([0, 1]);
    });

    it('should handle API errors gracefully', async () => {
      api.getStats.mockRejectedValue(new Error('Network error'));
      api.getDailyStats.mockRejectedValue(new Error('Network error'));
      api.getChartData.mockRejectedValue(new Error('Network error'));
      api.getRecentUploads.mockRejectedValue(new Error('Network error'));

      // Should not throw
      await expect(loadAllStats()).resolves.not.toThrow();

      // statsLoaded should remain false on error
      expect(get(statsLoaded)).toBe(false);
    });
  });

  describe('refreshChart', () => {
    it('should update only chart data', async () => {
      const mockChart = { labels: ['13:00'], uploaded: [20], hashed: [30], errors: [2] };
      api.getChartData.mockResolvedValue(mockChart);

      // Set some initial stats
      stats.set({ total_files: 100, uploaded_files: 50, unique_hashes: 90, total_bytes: 1000000 });

      await refreshChart();

      const chart = get(chartData);
      expect(chart.labels).toEqual(['13:00']);
      expect(chart.datasets[0].data).toEqual([20]);

      // Stats should remain unchanged
      expect(get(stats).total_files).toBe(100);
    });
  });

  describe('refreshRecentUploads', () => {
    it('should update only recent uploads', async () => {
      const mockRecent = { count: 5, total_bytes: 10000, uploads: [{ id: 1 }] };
      api.getRecentUploads.mockResolvedValue(mockRecent);

      await refreshRecentUploads();

      expect(get(recentUploads)).toEqual(mockRecent);
    });
  });
});
