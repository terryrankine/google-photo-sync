<script>
  import { Router, Route } from 'svelte-routing';
  import { QueryClient, QueryClientProvider } from '@tanstack/svelte-query';
  import Navbar from './lib/components/Navbar.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Jobs from './lib/pages/Jobs.svelte';
  import Stats from './lib/pages/Stats.svelte';
  import Files from './lib/pages/Files.svelte';
  import Logs from './lib/pages/Logs.svelte';
  import Config from './lib/pages/Config.svelte';
  import Setup from './lib/pages/Setup.svelte';

  // Create QueryClient with sensible defaults
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 1000 * 30, // 30 seconds
        refetchOnWindowFocus: true,
      },
    },
  });
</script>

<QueryClientProvider client={queryClient}>
  <Router>
    <div class="min-h-screen bg-gray-950 text-white">
      <Navbar />
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
</QueryClientProvider>
