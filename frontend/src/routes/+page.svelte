<script>
  import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';
  import StatsCard from '$lib/components/StatsCard.svelte';
  import LineChart from '$lib/components/LineChart.svelte';
  import WorkerProgress from '$lib/components/WorkerProgress.svelte';
  import QueueDepth from '$lib/components/QueueDepth.svelte';

  const queryClient = useQueryClient();

  // Dashboard query with auto-refresh
  const dashboardQuery = createQuery(() => ({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const res = await fetch('/api/dashboard');
      if (!res.ok) throw new Error('Failed to fetch dashboard');
      return res.json();
    },
    refetchInterval: 10000,
  }));

  // Live metrics - always poll, lightweight endpoint
  const liveQuery = createQuery(() => ({
    queryKey: ['live-metrics'],
    queryFn: async () => {
      const res = await fetch('/api/workers/live');
      if (!res.ok) throw new Error('Failed to fetch live metrics');
      return res.json();
    },
    refetchInterval: 2000,
  }));

  // Start job mutation
  const startMutation = createMutation(() => ({
    mutationFn: async () => {
      const res = await fetch('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!res.ok) throw new Error('Failed to start job');
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  }));

  // Pause job mutation
  const pauseMutation = createMutation(() => ({
    mutationFn: async (id) => {
      const res = await fetch(`/api/jobs/${id}/pause`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to pause job');
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  }));

  // Resume job mutation
  const resumeMutation = createMutation(() => ({
    mutationFn: async (id) => {
      const res = await fetch(`/api/jobs/${id}/resume`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to resume job');
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  }));

  // Cancel job mutation
  const cancelMutation = createMutation(() => ({
    mutationFn: async (id) => {
      const res = await fetch(`/api/jobs/${id}/cancel`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to cancel job');
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  }));

  // Derived data
  let stats = $derived(dashboardQuery.data?.stats || {});
  let activeJob = $derived(liveQuery.data?.job_progress || dashboardQuery.data?.active_job);
  let activity = $derived(dashboardQuery.data?.activity || []);
  let liveMetrics = $derived(liveQuery.data || { queue: { hash: {}, upload: {} }, hash_workers: [], upload_workers: [], summary: {} });

  let chartData = $derived({
    labels: dashboardQuery.data?.chart?.labels || [],
    datasets: [
      { label: 'Uploaded', data: dashboardQuery.data?.chart?.uploaded || [], borderColor: '#3b82f6', tension: 0.3 },
      { label: 'Hashed', data: dashboardQuery.data?.chart?.hashed || [], borderColor: '#10b981', tension: 0.3 },
      { label: 'Errors', data: dashboardQuery.data?.chart?.errors || [], borderColor: '#ef4444', tension: 0.3 }
    ]
  });

  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatNumber(n) {
    return new Intl.NumberFormat().format(n || 0);
  }

  function handleCancel() {
    if (activeJob && confirm('Cancel this job?')) {
      cancelMutation.mutate(activeJob.id);
    }
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <h1 class="text-3xl font-bold">Dashboard</h1>
    <button
      onclick={() => startMutation.mutate()}
      disabled={startMutation.isPending}
      class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
    >
      {startMutation.isPending ? 'Starting...' : 'Start New Sync'}
    </button>
  </div>

  <!-- Stats Cards -->
  <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
    <StatsCard title="Total Files" value={formatNumber(stats.total_files)} subtitle="{formatNumber(stats.uploaded_files)} uploaded" />
    <StatsCard title="Pending" value={formatNumber(stats.pending_files)} subtitle="{formatNumber(stats.error_files)} errors" />
    <StatsCard title="Database" value={formatBytes(dashboardQuery.data?.db_size_bytes)} subtitle="{formatNumber(stats.unique_hashes)} unique hashes" />
    <StatsCard title="Data" value={formatBytes(stats.uploaded_bytes)} subtitle="uploaded" />
  </div>

  <!-- Active Job -->
  {#if activeJob}
    <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xl font-semibold">
          Job #{activeJob.id}
          <span class="text-gray-400 text-lg ml-2">{activeJob.current_phase?.toUpperCase() || 'RUNNING'}</span>
        </h2>
        <div class="flex space-x-2">
          {#if activeJob.status === 'running'}
            <button onclick={() => pauseMutation.mutate(activeJob.id)} class="bg-yellow-600 hover:bg-yellow-700 px-3 py-1 rounded text-sm">Pause</button>
          {:else if activeJob.status === 'paused'}
            <button onclick={() => resumeMutation.mutate(activeJob.id)} class="bg-green-600 hover:bg-green-700 px-3 py-1 rounded text-sm">Resume</button>
          {/if}
          <button onclick={handleCancel} class="bg-red-600 hover:bg-red-700 px-3 py-1 rounded text-sm">Cancel</button>
        </div>
      </div>

      <!-- Progress bar -->
      <div class="mb-4">
        <div class="flex justify-between text-sm text-gray-400 mb-1">
          <span>{formatNumber(activeJob.files_uploaded)} / {formatNumber(activeJob.files_scanned)} files</span>
          <span>{(activeJob.progress_percent || 0).toFixed(1)}%</span>
        </div>
        <div class="w-full bg-gray-700 rounded-full h-3">
          <div class="bg-blue-600 h-3 rounded-full transition-all duration-300" style="width: {activeJob.progress_percent || 0}%"></div>
        </div>
      </div>

      <!-- Job stats -->
      <div class="grid grid-cols-4 gap-4 text-sm">
        <div><span class="text-gray-400">Scanned:</span> <span class="font-medium">{formatNumber(activeJob.files_scanned)}</span></div>
        <div><span class="text-gray-400">Hashed:</span> <span class="font-medium">{formatNumber(activeJob.files_hashed)}</span></div>
        <div><span class="text-gray-400">Uploaded:</span> <span class="font-medium">{formatNumber(activeJob.files_uploaded)}</span></div>
        <div><span class="text-gray-400">Errors:</span> <span class="font-medium text-red-400">{activeJob.files_errored || 0}</span></div>
      </div>
    </div>

    <!-- Queue Depths -->
    <QueueDepth queue={liveMetrics.queue} />

    <!-- Workers Grid -->
    {#if liveMetrics.hash_workers?.length > 0}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <WorkerProgress title="Hash Workers" workers={liveMetrics.hash_workers} totalThroughput={liveMetrics.summary?.hash_throughput_mbps || 0} totalFilesPerSec={liveMetrics.summary?.hash_files_per_second || 0} />
        <WorkerProgress title="Upload Workers" workers={liveMetrics.upload_workers || []} totalThroughput={liveMetrics.summary?.upload_throughput_mbps || 0} totalFilesPerSec={liveMetrics.summary?.upload_files_per_second || 0} />
      </div>
    {:else if liveMetrics.upload_workers?.length > 0}
      <WorkerProgress title="Upload Workers" workers={liveMetrics.upload_workers} totalThroughput={liveMetrics.summary?.upload_throughput_mbps || 0} totalFilesPerSec={liveMetrics.summary?.upload_files_per_second || 0} />
    {/if}
  {:else}
    <div class="bg-gray-800 rounded-lg p-6 border border-gray-700 text-center text-gray-400">
      No active job. Click "Start New Sync" to begin.
    </div>
  {/if}

  <!-- Chart -->
  {#if chartData.labels?.length > 0}
    <LineChart title="Last 7 Days" data={chartData} />
  {/if}

  <!-- Recent Activity -->
  {#if activity.length > 0}
    <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 class="text-xl font-semibold mb-4">Recent Activity</h2>
      <ul class="space-y-2 text-sm">
        {#each activity as event}
          <li class="flex items-start">
            <span class="text-gray-500 w-32 flex-shrink-0">{event.timestamp}</span>
            <span class:text-red-400={event.event_type === 'error'} class:text-gray-300={event.event_type !== 'error'}>{event.message}</span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</div>
