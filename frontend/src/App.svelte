<script>
  import { Router, Route } from 'svelte-routing';
  import { onMount, onDestroy } from 'svelte';
  import { api } from './lib/api.js';
  import { loadAllStats, statsLoaded } from './lib/stores/stats.js';
  import { loadJobs, jobsLoaded } from './lib/stores/jobs.js';
  import { loadAllConfig, configLoaded } from './lib/stores/config.js';
  import Navbar from './lib/components/Navbar.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Jobs from './lib/pages/Jobs.svelte';
  import Stats from './lib/pages/Stats.svelte';
  import Files from './lib/pages/Files.svelte';
  import Logs from './lib/pages/Logs.svelte';
  import Config from './lib/pages/Config.svelte';
  import Setup from './lib/pages/Setup.svelte';

  let status = 'idle';
  let interval;

  async function fetchStatus() {
    try {
      // Only fetch status - Dashboard page handles full dashboard data
      const data = await api.getStatus();
      status = data.status || 'idle';
    } catch (e) {
      console.error(e);
    }
  }

  async function preloadData() {
    // Preload all commonly needed data in parallel into stores
    // Pages will read from stores if already loaded
    const promises = [];

    if (!$statsLoaded) promises.push(loadAllStats());
    if (!$jobsLoaded) promises.push(loadJobs());
    if (!$configLoaded) promises.push(loadAllConfig());

    await Promise.all(promises);
  }

  onMount(() => {
    fetchStatus();
    preloadData();
    // Poll less frequently - dashboard page has its own polling
    interval = setInterval(fetchStatus, 30000);
  });

  onDestroy(() => {
    if (interval) clearInterval(interval);
  });
</script>

<Router>
  <div class="min-h-screen bg-gray-950 text-white">
    <Navbar {status} />
    <main class="max-w-7xl mx-auto px-4 py-8">
      <Route path="/" component={Dashboard} />
      <Route path="/jobs" component={Jobs} />
      <Route path="/stats" component={Stats} />
      <Route path="/files" component={Files} />
      <Route path="/logs" component={Logs} />
      <Route path="/config" component={Config} />
      <Route path="/setup" component={Setup} />
    </main>
    <footer class="border-t border-gray-800 mt-12">
      <div class="max-w-7xl mx-auto px-4 py-6 text-center text-gray-500 text-sm">
        Google Photos Sync Tool
      </div>
    </footer>
  </div>
</Router>
