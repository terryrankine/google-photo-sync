<script>
  import { createQuery } from '@tanstack/svelte-query';
  import { marked } from 'marked';

  // Configure marked for GitHub-flavored markdown
  marked.setOptions({
    gfm: true,
    breaks: true
  });

  const quickstartQuery = createQuery({
    queryKey: ['quickstart'],
    queryFn: async () => {
      const res = await fetch('/api/quickstart');
      if (!res.ok) throw new Error('Failed to fetch quickstart');
      return res.json();
    },
  });

  $: content = $quickstartQuery.data?.content || '';
  $: renderedHtml = content ? marked(content) : '';
</script>

<div class="max-w-4xl mx-auto">
  {#if $quickstartQuery.isLoading}
    <div class="text-center py-8 text-gray-400">Loading documentation...</div>
  {:else if $quickstartQuery.error}
    <div class="bg-red-900/50 border border-red-700 rounded-lg p-4 text-red-300">
      Failed to load documentation: {$quickstartQuery.error.message}
    </div>
  {:else}
    <article class="prose prose-invert max-w-none">
      {@html renderedHtml}
    </article>
  {/if}
</div>
