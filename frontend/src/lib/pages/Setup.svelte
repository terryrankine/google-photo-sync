<script>
  import { onMount } from 'svelte';
  import { api } from '../api.js';

  let content = '';
  let loading = true;
  let error = null;

  onMount(async () => {
    try {
      const data = await api.getQuickstart();
      content = data.content;
    } catch (e) {
      error = e.message;
    }
    loading = false;
  });

  // Simple markdown to HTML converter
  function renderMarkdown(md) {
    if (!md) return '';

    let html = md
      // Escape HTML
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')

      // Code blocks (```...```)
      .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre class="bg-gray-900 rounded-lg p-4 overflow-x-auto my-4 text-sm"><code class="text-green-400">${code.trim()}</code></pre>`;
      })

      // Inline code (`...`)
      .replace(/`([^`]+)`/g, '<code class="bg-gray-700 px-1.5 py-0.5 rounded text-sm text-yellow-300">$1</code>')

      // Headers
      .replace(/^### (.+)$/gm, '<h3 class="text-xl font-semibold mt-6 mb-3 text-white">$1</h3>')
      .replace(/^## (.+)$/gm, '<h2 class="text-2xl font-bold mt-8 mb-4 text-white border-b border-gray-700 pb-2">$1</h2>')
      .replace(/^# (.+)$/gm, '<h1 class="text-3xl font-bold mb-6 text-white">$1</h1>')

      // Horizontal rules
      .replace(/^---$/gm, '<hr class="border-gray-700 my-8">')

      // Bold
      .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-white">$1</strong>')

      // Links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-blue-400 hover:text-blue-300 underline">$1</a>')

      // Blockquotes
      .replace(/^&gt; (.+)$/gm, '<blockquote class="border-l-4 border-blue-500 pl-4 my-4 text-gray-300 italic">$1</blockquote>')

      // Tables - simplified handling
      .replace(/\|(.+)\|/g, (match) => {
        const cells = match.split('|').filter(c => c.trim());
        if (cells.some(c => /^[-:]+$/.test(c.trim()))) {
          return ''; // Skip separator row
        }
        const cellHtml = cells.map(c => `<td class="border border-gray-700 px-3 py-2">${c.trim()}</td>`).join('');
        return `<tr>${cellHtml}</tr>`;
      })

      // Unordered lists
      .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc list-inside text-gray-300">$1</li>')
      .replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal list-inside text-gray-300">$2</li>')

      // Paragraphs (double newlines)
      .replace(/\n\n/g, '</p><p class="text-gray-300 my-4">')

      // Single newlines in content
      .replace(/\n/g, '<br>');

    // Wrap in paragraph if not starting with block element
    if (!html.startsWith('<h') && !html.startsWith('<pre') && !html.startsWith('<hr')) {
      html = '<p class="text-gray-300 my-4">' + html + '</p>';
    }

    // Wrap consecutive table rows
    html = html.replace(/(<tr>.*?<\/tr>)+/gs, '<table class="w-full border-collapse my-4">$&</table>');

    // Wrap consecutive list items
    html = html.replace(/(<li[^>]*>.*?<\/li>\s*)+/gs, '<ul class="my-4">$&</ul>');

    return html;
  }
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
      {@html renderMarkdown(content)}
    </article>
  {/if}
</div>
