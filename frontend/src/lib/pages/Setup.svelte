<script>
  import { onMount } from 'svelte';
  import { marked } from 'marked';
  import { api } from '../api.js';

  let content = '';
  let loading = true;
  let error = null;

  // Configure marked for GitHub-flavored markdown
  marked.setOptions({
    gfm: true,
    breaks: true
  });

  onMount(async () => {
    try {
      const data = await api.getQuickstart();
      content = data.content;
    } catch (e) {
      error = e.message;
    }
    loading = false;
  });

  $: renderedHtml = content ? marked(content) : '';
</script>

<div class="max-w-4xl mx-auto">
  {#if loading}
    <div class="text-center py-8 text-gray-400">Loading documentation...</div>
  {:else if error}
    <div class="bg-red-900/50 border border-red-700 rounded-lg p-4 text-red-300">
      Failed to load documentation: {error}
    </div>
  {:else}
    <article class="prose prose-invert max-w-none">
      {@html renderedHtml}
    </article>
  {/if}
</div>
