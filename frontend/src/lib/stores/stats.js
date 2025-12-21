import { writable } from 'svelte/store';
import { api } from '../api.js';

// Cached stats data
export const stats = writable({ total_files: 0, uploaded_files: 0, unique_hashes: 0, total_bytes: 0 });
export const dailyStats = writable([]);
export const chartData = writable({ labels: [], datasets: [] });
export const recentUploads = writable({ count: 0, total_bytes: 0, uploads: [] });
export const statsLoaded = writable(false);

// Load all stats data
export async function loadAllStats() {
  try {
    const [statsData, daily, chart, recent] = await Promise.all([
      api.getStats(),
      api.getDailyStats(),
      api.getChartData(),
      api.getRecentUploads(5, 5)
    ]);

    stats.set(statsData);
    dailyStats.set(daily);
    chartData.set({
      labels: chart.labels || [],
      datasets: [
        { label: 'Uploaded', data: chart.uploaded || [], borderColor: '#3b82f6', tension: 0.3 },
        { label: 'Hashed', data: chart.hashed || [], borderColor: '#10b981', tension: 0.3 },
        { label: 'Errors', data: chart.errors || [], borderColor: '#ef4444', tension: 0.3 }
      ]
    });
    recentUploads.set(recent);
    statsLoaded.set(true);
  } catch (e) {
    console.error('Failed to load stats:', e);
  }
}

// Refresh just chart data
export async function refreshChart() {
  try {
    const chart = await api.getChartData();
    chartData.set({
      labels: chart.labels || [],
      datasets: [
        { label: 'Uploaded', data: chart.uploaded || [], borderColor: '#3b82f6', tension: 0.3 },
        { label: 'Hashed', data: chart.hashed || [], borderColor: '#10b981', tension: 0.3 },
        { label: 'Errors', data: chart.errors || [], borderColor: '#ef4444', tension: 0.3 }
      ]
    });
  } catch (e) {
    console.error('Failed to refresh chart:', e);
  }
}

// Refresh recent uploads
export async function refreshRecentUploads() {
  try {
    const recent = await api.getRecentUploads(5, 5);
    recentUploads.set(recent);
  } catch (e) {
    console.error('Failed to refresh recent uploads:', e);
  }
}
