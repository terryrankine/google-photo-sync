<script>
  import { createQuery } from '@tanstack/svelte-query';
  import { LayoutDashboard, ListTodo, BarChart3, Files, ScrollText, Settings, BookOpen } from 'lucide-svelte';

  const statusQuery = createQuery(() => ({
    queryKey: ['status'],
    queryFn: async () => {
      const res = await fetch('/api/status');
      if (!res.ok) throw new Error('Failed to fetch status');
      return res.json();
    },
    refetchInterval: 30000, // Poll every 30s
  }));

  let status = $derived(statusQuery.data?.status || 'idle');
</script>

<nav class="bg-gray-900 border-b border-gray-800 sticky top-0 z-50">
  <div class="max-w-7xl mx-auto px-4">
    <div class="flex items-center justify-between h-16">
      <div class="flex items-center space-x-8">
        <a href="/" class="text-xl font-bold text-white">GPhoto Sync</a>
        <div class="flex space-x-1">
          <a href="/" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><LayoutDashboard class="w-4 h-4" />Dashboard</a>
          <a href="/jobs" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><ListTodo class="w-4 h-4" />Jobs</a>
          <a href="/stats" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><BarChart3 class="w-4 h-4" />Statistics</a>
          <a href="/files" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><Files class="w-4 h-4" />Files</a>
          <a href="/logs" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><ScrollText class="w-4 h-4" />Logs</a>
          <a href="/config" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><Settings class="w-4 h-4" />Settings</a>
          <a href="/setup" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><BookOpen class="w-4 h-4" />Setup</a>
        </div>
      </div>
      <div class="flex items-center space-x-2">
        <span class="w-2 h-2 rounded-full" class:bg-green-500={status === 'idle'} class:bg-blue-500={status === 'running'} class:bg-yellow-500={status === 'paused'}></span>
        <span class="text-gray-400 text-sm capitalize">{status}</span>
      </div>
    </div>
  </div>
</nav>
