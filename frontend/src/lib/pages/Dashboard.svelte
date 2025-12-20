<script>
  import { onMount, onDestroy } from 'svelte';
  import { api } from '../api.js';
  import StatsCard from '../components/StatsCard.svelte';
  import LineChart from '../components/LineChart.svelte';
  import WorkerProgress from '../components/WorkerProgress.svelte';
  import QueueDepth from '../components/QueueDepth.svelte';

  let stats = { total_files: 0, uploaded_files: 0, unique_hashes: 0 };
  let activeJob = null;
  let chartData = { labels: [], datasets: [] };
  let activity = [];
  let dbSize = '0 KB';
  let interval;

  // Live metrics state
  let liveMetrics = {
    queue: { hash: {}, upload: {} },
    hash_workers: [],
    upload_workers: [],
    summary: {}
  };
  let liveInterval;

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatNumber(n) {
    return new Intl.NumberFormat().format(n);
  }

  async function fetchDashboard() {
    try {
      const data = await api.getDashboard();

      stats = data.stats || {};
      activeJob = data.active_job;
      activity = data.activity || [];
      dbSize = formatBytes(data.db_size_bytes || 0);

      // Update chart
      const chart = data.chart || {};
      chartData = {
        labels: chart.labels || [],
        datasets: [
          { label: 'Uploaded', data: chart.uploaded || [], borderColor: '#3b82f6', tension: 0.3 },
          { label: 'Hashed', data: chart.hashed || [], borderColor: '#10b981', tension: 0.3 },
          { label: 'Errors', data: chart.errors || [], borderColor: '#ef4444', tension: 0.3 }
        ]
      };

      // Start/stop live polling based on job state
      if (activeJob && !liveInterval) {
        startLivePolling();
      } else if (!activeJob && liveInterval) {
        stopLivePolling();
      }
    } catch (e) {
      console.error('Dashboard fetch error:', e);
    }
  }

  async function fetchLiveMetrics() {
    try {
      liveMetrics = await api.getLiveMetrics();
      // Update activeJob from live metrics if available
      if (liveMetrics.job_progress) {
        activeJob = liveMetrics.job_progress;
      }
    } catch (e) {
      console.error('Live metrics error:', e);
    }
  }

  function startLivePolling() {
    if (liveInterval) return;
    fetchLiveMetrics();
    liveInterval = setInterval(fetchLiveMetrics, 1500);
  }

  function stopLivePolling() {
    if (liveInterval) {
      clearInterval(liveInterval);
      liveInterval = null;
    }
    // Reset live metrics
    liveMetrics = {
      queue: { hash: {}, upload: {} },
      hash_workers: [],
      upload_workers: [],
      summary: {}
    };
  }

  async function startSync() {
    try {
      await api.startBatch();
      await fetchDashboard();
      startLivePolling();
    } catch (e) {
      console.error('Start error:', e);
    }
  }

  async function pauseJob() {
    if (activeJob) {
      await api.pauseJob(activeJob.id);
      await fetchDashboard();
    }
  }

  async function resumeJob() {
    if (activeJob) {
      await api.resumeJob(activeJob.id);
      await fetchDashboard();
    }
  }

  async function cancelJob() {
    if (activeJob && confirm('Cancel this job?')) {
      await api.cancelJob(activeJob.id);
      stopLivePolling();
      await fetchDashboard();
    }
  }

  onMount(() => {
    fetchDashboard();
    interval = setInterval(fetchDashboard, 10000);
  });

  onDestroy(() => {
    if (interval) clearInterval(interval);
    stopLivePolling();
  });
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <h1 class="text-3xl font-bold">Dashboard</h1>
    <button on:click={startSync} class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg font-medium transition-colors">
      Start New Sync
    </button>
  </div>

  <!-- Stats Cards -->
  <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
    <StatsCard title="Total Files" value={formatNumber(stats.total_files)} subtitle="{formatNumber(stats.uploaded_files)} uploaded" />
    <StatsCard title="Pending" value={formatNumber(stats.pending_files || 0)} subtitle="{formatNumber(stats.error_files || 0)} errors" />
    <StatsCard title="Database" value={dbSize} subtitle="{formatNumber(stats.unique_hashes)} unique hashes" />
    <StatsCard title="Data" value={formatBytes(stats.uploaded_bytes || 0)} subtitle="uploaded" />
  </div>

  <!-- Active Job -->
  {#if activeJob}
    <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xl font-semibold">
          Job #{activeJob.id}
          <span class="text-gray-400 text-lg ml-2">
            {activeJob.current_phase?.toUpperCase() || 'RUNNING'}
          </span>
        </h2>
        <div class="flex space-x-2">
          {#if activeJob.status === 'running'}
            <button on:click={pauseJob} class="bg-yellow-600 hover:bg-yellow-700 px-3 py-1 rounded text-sm">Pause</button>
          {:else if activeJob.status === 'paused'}
            <button on:click={resumeJob} class="bg-green-600 hover:bg-green-700 px-3 py-1 rounded text-sm">Resume</button>
          {/if}
          <button on:click={cancelJob} class="bg-red-600 hover:bg-red-700 px-3 py-1 rounded text-sm">Cancel</button>
        </div>
      </div>

      <!-- Progress bar -->
      <div class="mb-4">
        <div class="flex justify-between text-sm text-gray-400 mb-1">
          <span>
            {formatNumber(activeJob.files_uploaded || 0)} / {formatNumber(activeJob.files_scanned || 0)} files
          </span>
          <span>{(activeJob.progress_percent || 0).toFixed(1)}%</span>
        </div>
        <div class="w-full bg-gray-700 rounded-full h-3">
          <div class="bg-blue-600 h-3 rounded-full transition-all duration-300" style="width: {activeJob.progress_percent || 0}%"></div>
        </div>
      </div>

      <!-- Job stats -->
      <div class="grid grid-cols-4 gap-4 text-sm">
        <div><span class="text-gray-400">Scanned:</span> <span class="font-medium">{formatNumber(activeJob.files_scanned || 0)}</span></div>
        <div><span class="text-gray-400">Hashed:</span> <span class="font-medium">{formatNumber(activeJob.files_hashed || 0)}</span></div>
        <div><span class="text-gray-400">Uploaded:</span> <span class="font-medium">{formatNumber(activeJob.files_uploaded || 0)}</span></div>
        <div><span class="text-gray-400">Errors:</span> <span class="font-medium text-red-400">{activeJob.files_errored || 0}</span></div>
      </div>
    </div>

    <!-- Queue Depths -->
    <QueueDepth queue={liveMetrics.queue} />

    <!-- Workers Grid -->
    {#if liveMetrics.hash_workers?.length > 0}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <WorkerProgress
          title="Hash Workers"
          workers={liveMetrics.hash_workers}
          totalThroughput={liveMetrics.summary?.hash_throughput_mbps || 0}
          totalFilesPerSec={liveMetrics.summary?.hash_files_per_second || 0}
        />
        <WorkerProgress
          title="Upload Workers"
          workers={liveMetrics.upload_workers || []}
          totalThroughput={liveMetrics.summary?.upload_throughput_mbps || 0}
          totalFilesPerSec={liveMetrics.summary?.upload_files_per_second || 0}
        />
      </div>
    {:else if liveMetrics.upload_workers?.length > 0}
      <!-- Full width when only upload workers are active -->
      <WorkerProgress
        title="Upload Workers"
        workers={liveMetrics.upload_workers}
        totalThroughput={liveMetrics.summary?.upload_throughput_mbps || 0}
        totalFilesPerSec={liveMetrics.summary?.upload_files_per_second || 0}
      />
    {/if}
  {:else}
    <div class="bg-gray-800 rounded-lg p-6 border border-gray-700 text-center text-gray-400">
      No active job. Click "Start New Sync" to begin.
    </div>
  {/if}

  <!-- Chart - only show if there's data -->
  {#if chartData.labels?.length > 0}
    <LineChart title="Last 7 Days" data={chartData} />
  {/if}

  <!-- Recent Activity - only show if there's activity -->
  {#if activity.length > 0}
    <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 class="text-xl font-semibold mb-4">Recent Activity</h2>
      <ul class="space-y-2 text-sm">
        {#each activity as event}
          <li class="flex items-start">
            <span class="text-gray-500 w-32 flex-shrink-0">{event.timestamp}</span>
            <span class:text-red-400={event.event_type === 'error'} class:text-gray-300={event.event_type !== 'error'}>
              {event.message}
            </span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</div>
