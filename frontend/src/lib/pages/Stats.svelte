<script>
  import { onMount } from 'svelte';
  import { api } from '../api.js';
  import LineChart from '../components/LineChart.svelte';

  let chartData = { labels: [], datasets: [] };
  let dailyStats = [];
  let stats = { total_files: 0, uploaded_files: 0, unique_hashes: 0, total_bytes: 0 };

  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  onMount(async () => {
    try {
      // Load overview stats
      stats = await api.getStats();

      const data = await api.getChartData();
      chartData = {
        labels: data.labels || [],
        datasets: [
          { label: 'Uploaded', data: data.uploaded || [], borderColor: '#3b82f6', tension: 0.3 },
          { label: 'Hashed', data: data.hashed || [], borderColor: '#10b981', tension: 0.3 },
          { label: 'Errors', data: data.errors || [], borderColor: '#ef4444', tension: 0.3 }
        ]
      };

      dailyStats = await api.getDailyStats();
    } catch (e) {
      console.error(e);
    }
  });
</script>

<div class="space-y-8">
  <h1 class="text-3xl font-bold">Statistics</h1>

  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <h2 class="text-xl font-semibold mb-4">Overview</h2>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="text-center">
        <div class="text-3xl font-bold text-blue-400">{stats.total_files || 0}</div>
        <div class="text-gray-400">Total Files</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold text-green-400">{stats.uploaded_files || 0}</div>
        <div class="text-gray-400">Uploaded</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold text-purple-400">{stats.unique_hashes || 0}</div>
        <div class="text-gray-400">Unique Hashes</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold text-yellow-400">{formatBytes(stats.total_bytes)}</div>
        <div class="text-gray-400">Total Size</div>
      </div>
    </div>
  </div>

  <LineChart title="Upload Activity" data={chartData} />

  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <h2 class="text-xl font-semibold mb-4">Daily Stats</h2>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-gray-400 border-b border-gray-700">
          <th class="pb-2">Date</th>
          <th class="pb-2 text-right">Files Hashed</th>
          <th class="pb-2 text-right">Files Uploaded</th>
          <th class="pb-2 text-right">Data Read</th>
          <th class="pb-2 text-right">Data Uploaded</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-700">
        {#each dailyStats as day}
          <tr>
            <td class="py-2">{day.date}</td>
            <td class="py-2 text-right">{day.files_hashed || 0}</td>
            <td class="py-2 text-right">{day.files_uploaded || 0}</td>
            <td class="py-2 text-right">{formatBytes(day.bytes_read)}</td>
            <td class="py-2 text-right text-green-400">{formatBytes(day.bytes_uploaded)}</td>
          </tr>
        {:else}
          <tr>
            <td colspan="5" class="py-4 text-center text-gray-500">No data yet</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>
