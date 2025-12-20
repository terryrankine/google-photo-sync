<script>
  import { link } from 'svelte-routing';
  export let status = 'idle';
</script>

<nav class="bg-gray-900 border-b border-gray-800 sticky top-0 z-50">
  <div class="max-w-7xl mx-auto px-4">
    <div class="flex items-center justify-between h-16">
      <div class="flex items-center space-x-8">
        <a href="/" use:link class="text-xl font-bold text-white">GPhoto Sync</a>
        <div class="flex space-x-4">
          <a href="/" use:link class="text-gray-300 hover:text-white px-3 py-2 rounded-md text-sm font-medium">Dashboard</a>
          <a href="/jobs" use:link class="text-gray-300 hover:text-white px-3 py-2 rounded-md text-sm font-medium">Jobs</a>
          <a href="/stats" use:link class="text-gray-300 hover:text-white px-3 py-2 rounded-md text-sm font-medium">Statistics</a>
          <a href="/files" use:link class="text-gray-300 hover:text-white px-3 py-2 rounded-md text-sm font-medium">Files</a>
          <a href="/config" use:link class="text-gray-300 hover:text-white px-3 py-2 rounded-md text-sm font-medium">Settings</a>
        </div>
      </div>
      <div class="flex items-center space-x-2">
        <span class="w-2 h-2 rounded-full" class:bg-green-500={status === 'idle'} class:bg-blue-500={status === 'running'} class:bg-yellow-500={status === 'paused'}></span>
        <span class="text-gray-400 text-sm capitalize">{status}</span>
      </div>
    </div>
  </div>
</nav>

