<script>
  import { createQuery } from '@tanstack/svelte-query';
  import { marked } from 'marked';

  // Configure marked for GitHub-flavored markdown
  marked.setOptions({
    gfm: true,
    breaks: true
  });

  const quickstartQuery = createQuery(() => ({
    queryKey: ['quickstart'],
    queryFn: async () => {
      const res = await fetch('/api/quickstart');
      if (!res.ok) throw new Error('Failed to fetch quickstart');
      return res.json();
    },
  }));

  // Svelte 5 derived values
  let content = $derived(quickstartQuery.data?.content || '');
  let renderedHtml = $derived(content ? marked(content) : '');
</script>

<div class="max-w-4xl mx-auto">
  {#if quickstartQuery.isLoading}
    <div class="text-center py-8 text-gray-400">Loading documentation...</div>
  {:else if quickstartQuery.error}
    <div class="bg-red-900/50 border border-red-700 rounded-lg p-4 text-red-300">
      Failed to load documentation: {quickstartQuery.error.message}
    </div>
  {:else}
    <article class="prose prose-lg prose-invert max-w-none prose-headings:text-gray-100 prose-p:text-gray-300 prose-code:text-blue-300 prose-pre:bg-gray-800">
      {@html renderedHtml}
    </article>
  {/if}
</div>
