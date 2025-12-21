<script>
  import { browser } from '$app/environment';
  import { QueryClient, QueryClientProvider } from '@tanstack/svelte-query';
  import Navbar from '$lib/components/Navbar.svelte';
  import '../app.css';

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
  <div class="min-h-screen bg-gray-950 text-white">
    <Navbar />
    <main class="max-w-7xl mx-auto px-4 py-8">
      <slot />
    </main>
    <footer class="border-t border-gray-800 mt-12">
      <div class="max-w-7xl mx-auto px-4 py-6 text-center text-gray-500 text-sm">
        Google Photos Sync Tool
      </div>
    </footer>
  </div>
</QueryClientProvider>
