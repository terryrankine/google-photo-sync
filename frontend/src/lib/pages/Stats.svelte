<script>
  import { onMount, onDestroy } from 'svelte';
  import LineChart from '../components/LineChart.svelte';
  import {
    stats, dailyStats, chartData, recentUploads, statsLoaded,
    loadAllStats, refreshChart, refreshRecentUploads
  } from '../stores/stats.js';

  let pollInterval;
  let recentInterval;

  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatTimeAgo(minutes) {
    if (!minutes || minutes < 1) return 'just now';
    if (minutes === 1) return '1 min ago';
    return `${minutes} min ago`;
  }

  onMount(async () => {
    // Load immediately if not already loaded, otherwise refresh in background
    if (!$statsLoaded) {
      await loadAllStats();
    } else {
      loadAllStats();  // Refresh in background
    }

    // Poll chart every 60 seconds, recent uploads every 30 seconds
    pollInterval = setInterval(refreshChart, 60000);
    recentInterval = setInterval(refreshRecentUploads, 30000);
  });

  onDestroy(() => {
    if (pollInterval) clearInterval(pollInterval);
    if (recentInterval) clearInterval(recentInterval);
  });
</script>

<div class="space-y-6">
  <h1 class="text-3xl font-bold">Statistics</h1>

  <!-- Overview -->
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <h2 class="text-xl font-semibold mb-4">Overview</h2>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="text-center">
        <div class="text-3xl font-bold text-blue-400">{$stats.total_files || 0}</div>
        <div class="text-gray-400">Total Files</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold text-green-400">{$stats.uploaded_files || 0}</div>
        <div class="text-gray-400">Uploaded</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold text-purple-400">{$stats.unique_hashes || 0}</div>
        <div class="text-gray-400">Unique Hashes</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold text-yellow-400">{formatBytes($stats.total_bytes)}</div>
        <div class="text-gray-400">Total Size</div>
      </div>
    </div>
  </div>

  <!-- Activity Chart -->
  <LineChart title="Activity (5-min intervals)" data={$chartData} dualAxis={true} />

  <!-- Recent Uploads -->
  <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
    <div class="flex justify-between items-center mb-2">
      <h2 class="text-lg font-semibold">Recent Uploads</h2>
      <div class="text-sm text-gray-400">
        {$recentUploads.count} in last 5 min ({formatBytes($recentUploads.total_bytes)})
      </div>
    </div>
    {#if $recentUploads.uploads && $recentUploads.uploads.length > 0}
      <table class="w-full text-xs font-mono">
        <thead>
          <tr class="text-left text-gray-500 border-b border-gray-700">
            <th class="pb-1 w-10"></th>
            <th class="pb-1">File</th>
            <th class="pb-1">Media ID</th>
            <th class="pb-1 text-right">Size</th>
            <th class="pb-1 text-right w-20">When</th>
          </tr>
        </thead>
        <tbody>
          {#each $recentUploads.uploads as upload}
            <tr class="border-b border-gray-700/50 hover:bg-gray-700/30">
              <td class="py-1">
                <a href={upload.preview_url} target="_blank" class="block">
                  <img
                    src={upload.preview_url}
                    alt=""
                    class="w-8 h-8 object-cover rounded"
                    loading="lazy"
                    on:error={(e) => e.target.style.display = 'none'}
                  />
                </a>
              </td>
              <td class="py-1 truncate max-w-[200px]" title={upload.relative_path}>
                {#if upload.media_id}
                  <a
                    href="https://photos.google.com/lr/photo/{upload.media_id}"
                    target="_blank"
                    class="text-blue-400 hover:text-blue-300 hover:underline"
                  >
                    {upload.relative_path}
                  </a>
                {:else}
                  <span class="text-gray-300">{upload.relative_path}</span>
                {/if}
              </td>
              <td class="py-1 text-gray-500 truncate max-w-[120px]" title={upload.media_id || ''}>
                {#if upload.media_id}
                  <a
                    href="https://photos.google.com/lr/photo/{upload.media_id}"
                    target="_blank"
                    class="hover:text-blue-400"
                  >
                    {upload.media_id.slice(0, 16)}...
                  </a>
                {:else}
                  <span class="text-gray-600">-</span>
                {/if}
              </td>
              <td class="py-1 text-gray-500 text-right whitespace-nowrap">
                {formatBytes(upload.size)}
              </td>
              <td class="py-1 text-gray-500 text-right whitespace-nowrap">
                {formatTimeAgo(upload.minutes_ago)}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {:else}
      <div class="text-gray-500 text-center py-2 text-sm">No recent uploads</div>
    {/if}
  </div>

  <!-- Daily Stats -->
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
        {#each $dailyStats as day}
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
