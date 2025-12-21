<script>
  import { createQuery } from '@tanstack/svelte-query';

  // Pagination & sorting state
  let pageIndex = 0;
  let pageSize = 50;
  let sortBy = 'relative_path';
  let sortDesc = false;
  let globalFilter = '';
  let statusFilter = '';
  let searchTimeout;

  // Preview modal state
  let previewFile = null;

  // Build query params from state
  $: queryParams = {
    page: pageIndex + 1,
    limit: pageSize,
    search: globalFilter,
    status: statusFilter,
    sortBy,
    sortDir: sortDesc ? 'desc' : 'asc',
  };

  // Fetch files with createQuery
  $: filesQuery = createQuery({
    queryKey: ['files', queryParams],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(queryParams.page),
        limit: String(queryParams.limit),
      });
      if (queryParams.search) params.set('search', queryParams.search);
      if (queryParams.status) params.set('status', queryParams.status);
      if (queryParams.sortBy) params.set('sort_by', queryParams.sortBy);
      if (queryParams.sortDir) params.set('sort_dir', queryParams.sortDir);

      const res = await fetch(`/api/files?${params}`);
      if (!res.ok) throw new Error('Failed to fetch files');
      return res.json();
    },
    keepPreviousData: true,
  });

  $: files = $filesQuery.data?.files || [];
  $: total = $filesQuery.data?.total || 0;
  $: pageCount = Math.ceil(total / pageSize) || 1;

  // Helper functions
  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatDate(timestamp) {
    if (!timestamp) return '-';
    return new Date(timestamp * 1000).toLocaleDateString();
  }

  function getStatus(file) {
    if (file.status === 'error') return { text: 'Error', class: 'text-red-400' };
    if (file.media_id) return { text: 'Uploaded', class: 'text-green-400' };
    if (file.sha256) return { text: 'Hashed', class: 'text-blue-400' };
    return { text: 'Pending', class: 'text-gray-400' };
  }

  // Sorting
  function toggleSort(column) {
    if (sortBy === column) {
      sortDesc = !sortDesc;
    } else {
      sortBy = column;
      sortDesc = false;
    }
    pageIndex = 0;
  }

  function getSortIndicator(column) {
    if (sortBy !== column) return '';
    return sortDesc ? ' ▼' : ' ▲';
  }

  // Pagination
  function previousPage() {
    if (pageIndex > 0) pageIndex--;
  }

  function nextPage() {
    if (pageIndex < pageCount - 1) pageIndex++;
  }

  // Search with debounce
  function handleSearch(e) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      globalFilter = e.target.value;
      pageIndex = 0;
    }, 300);
  }

  function handleFilter() {
    pageIndex = 0;
  }

  // Preview
  function openPreview(file) {
    const previewable = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'mp4', 'mov', 'avi', 'mkv', '3gp'];
    const ext = (file.extension || '').toLowerCase();
    if (previewable.includes(ext)) previewFile = file;
  }

  function closePreview() {
    previewFile = null;
  }

  function isImage(ext) {
    return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif'].includes((ext || '').toLowerCase());
  }

  function isVideo(ext) {
    return ['mp4', 'mov', 'avi', 'mkv', '3gp'].includes((ext || '').toLowerCase());
  }

  function handleKeydown(e) {
    if (previewFile && e.key === 'Escape') closePreview();
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="space-y-6">
  <h1 class="text-3xl font-bold">Files</h1>

  <div class="flex gap-4 items-center">
    <input
      type="text"
      on:input={handleSearch}
      placeholder="Search files..."
      class="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
    />
    <select
      bind:value={statusFilter}
      on:change={handleFilter}
      class="px-4 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
    >
      <option value="">All</option>
      <option value="pending">Pending</option>
      <option value="uploaded">Uploaded</option>
      <option value="error">Error</option>
    </select>
  </div>

  <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-900">
          <th class="px-4 py-3 cursor-pointer hover:text-white select-none" on:click={() => toggleSort('relative_path')}>
            Path{getSortIndicator('relative_path')}
          </th>
          <th class="px-4 py-3 cursor-pointer hover:text-white select-none text-right" on:click={() => toggleSort('size')}>
            Size{getSortIndicator('size')}
          </th>
          <th class="px-4 py-3">Status</th>
          <th class="px-4 py-3 cursor-pointer hover:text-white select-none text-right" on:click={() => toggleSort('mtime')}>
            Modified{getSortIndicator('mtime')}
          </th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-700">
        {#each files as file}
          <tr class="hover:bg-gray-750 cursor-pointer" on:click={() => openPreview(file)}>
            <td class="px-4 py-3 font-mono text-xs truncate max-w-md">{file.relative_path}</td>
            <td class="px-4 py-3 text-right text-gray-400">{formatBytes(file.size)}</td>
            <td class="px-4 py-3">
              <span class={getStatus(file).class}>{getStatus(file).text}</span>
            </td>
            <td class="px-4 py-3 text-right text-gray-500">{formatDate(file.mtime)}</td>
          </tr>
        {:else}
          <tr>
            <td colspan="4" class="px-4 py-8 text-center text-gray-500">
              {$filesQuery.isLoading ? 'Loading...' : 'No files yet'}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <!-- Pagination -->
  <div class="flex justify-between items-center">
    <button
      on:click={previousPage}
      disabled={pageIndex === 0}
      class="px-4 py-2 bg-gray-700 rounded disabled:opacity-50 hover:bg-gray-600"
    >
      Previous
    </button>
    <span class="text-gray-400">
      Page {pageIndex + 1} of {pageCount}
      {#if total}
        ({total} total)
      {/if}
    </span>
    <button
      on:click={nextPage}
      disabled={pageIndex >= pageCount - 1}
      class="px-4 py-2 bg-gray-700 rounded disabled:opacity-50 hover:bg-gray-600"
    >
      Next
    </button>
  </div>
</div>

<!-- Preview Modal -->
{#if previewFile}
  <div class="fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center z-50" role="dialog" aria-modal="true" on:click={closePreview} on:keydown={(e) => e.key === 'Escape' && closePreview()}>
    <div class="relative max-w-4xl max-h-[90vh] bg-gray-900 rounded-lg overflow-hidden" on:click|stopPropagation on:keydown|stopPropagation>
      <button class="absolute top-2 right-2 z-10 p-2 bg-gray-800 rounded-full hover:bg-gray-700 text-white" on:click={closePreview} aria-label="Close preview">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      <div class="p-4 border-b border-gray-700">
        <p class="text-sm text-gray-400 truncate">{previewFile.relative_path}</p>
        <p class="text-xs text-gray-500 mt-1">{formatBytes(previewFile.size)} · {previewFile.extension?.toUpperCase() || 'Unknown'}</p>
      </div>
      <div class="flex items-center justify-center p-4 min-h-[300px]">
        {#if isImage(previewFile.extension)}
          <img src="/api/files/{previewFile.id}/preview" alt={previewFile.filename} class="max-w-full max-h-[70vh] object-contain" />
        {:else if isVideo(previewFile.extension)}
          <video src="/api/files/{previewFile.id}/preview" controls class="max-w-full max-h-[70vh]">
            <track kind="captions" />
            Your browser does not support video playback.
          </video>
        {/if}
      </div>
    </div>
  </div>
{/if}
