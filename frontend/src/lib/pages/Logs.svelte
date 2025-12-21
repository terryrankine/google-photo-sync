<script>
  import { createQuery, useQueryClient } from '@tanstack/svelte-query';

  const queryClient = useQueryClient();

  let levelFilter = '';
  let autoRefresh = true;

  // Logs query with conditional auto-refresh
  $: logsQuery = createQuery({
    queryKey: ['logs', levelFilter],
    queryFn: async () => {
      let url = '/api/logs?limit=200';
      if (levelFilter) url += `&level=${encodeURIComponent(levelFilter)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to fetch logs');
      return res.json();
    },
    refetchInterval: autoRefresh ? 2000 : false,
  });

  $: logs = $logsQuery.data || [];

  function getLevelClass(level) {
    switch (level) {
      case 'ERROR': return 'text-red-400';
      case 'WARNING': return 'text-yellow-400';
      case 'INFO': return 'text-blue-400';
      case 'DEBUG': return 'text-gray-500';
      default: return 'text-gray-300';
    }
  }

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['logs'] });
  }
</script>

<div class="space-y-4">
  <div class="flex items-center justify-between">
    <h1 class="text-3xl font-bold">Logs</h1>
    <div class="flex gap-4 items-center">
      <select bind:value={levelFilter} class="px-3 py-1 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500">
        <option value="">All Levels</option>
        <option value="ERROR">ERROR</option>
        <option value="WARNING">WARNING</option>
        <option value="INFO">INFO</option>
        <option value="DEBUG">DEBUG</option>
      </select>
      <button on:click={() => autoRefresh = !autoRefresh} class="px-3 py-1 rounded text-sm {autoRefresh ? 'bg-green-600' : 'bg-gray-600'}">
        {autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
      </button>
      <button on:click={refresh} class="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm">
        Refresh
      </button>
    </div>
  </div>

  <div class="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
    <div class="overflow-y-auto max-h-[70vh] font-mono text-xs">
      {#each logs as log}
        <div class="px-3 py-1 border-b border-gray-800 hover:bg-gray-800">
          <span class="text-gray-500">{log.timestamp}</span>
          <span class={getLevelClass(log.level)}>[{log.level}]</span>
          <span class="text-gray-400">{log.logger}:</span>
          <span class="text-gray-200">{log.message}</span>
        </div>
      {:else}
        <div class="px-4 py-8 text-center text-gray-500">
          {$logsQuery.isLoading ? 'Loading...' : 'No logs yet'}
        </div>
      {/each}
    </div>
  </div>
</div>
