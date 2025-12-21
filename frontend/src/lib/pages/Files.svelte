<script>
  import { onMount } from 'svelte';
  import { api } from '../api.js';

  let files = [];
  let page = 1;
  let total = 0;
  let hasMore = true;
  let search = '';
  let statusFilter = '';
  let searchTimeout;

  // Preview modal state
  let previewFile = null;
  let previewLoading = false;

  // Sort state
  let sortColumn = 'relative_path';
  let sortDirection = 'asc';

  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatDate(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString();
  }

  async function loadFiles() {
    try {
      const data = await api.getFiles(page, 50, search, statusFilter, sortColumn, sortDirection);
      files = data.files || data || [];
      total = data.total || files.length;
      hasMore = files.length === 50;
    } catch (e) {
      console.error(e);
    }
  }

  function handleSearch(e) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      page = 1;
      loadFiles();
    }, 300);
  }

  function handleFilter() {
    page = 1;
    loadFiles();
  }

  function toggleSort(column) {
    if (sortColumn === column) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortColumn = column;
      sortDirection = 'asc';
    }
    page = 1;
    loadFiles();
  }

  function getSortIcon(column) {
    if (sortColumn !== column) return '';
    return sortDirection === 'asc' ? ' ▲' : ' ▼';
  }

  function nextPage() {
    page++;
    loadFiles();
  }

  function prevPage() {
    if (page > 1) {
      page--;
      loadFiles();
    }
  }

  function openPreview(file) {
    const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif'];
    const videoExts = ['mp4', 'mov', 'avi', 'mkv', '3gp'];
    const ext = (file.extension || '').toLowerCase();

    if (imageExts.includes(ext) || videoExts.includes(ext)) {
      previewFile = file;
      previewLoading = true;
    }
  }

  function closePreview() {
    previewFile = null;
    previewLoading = false;
  }

  function getPreviewableFiles() {
    const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif'];
    const videoExts = ['mp4', 'mov', 'avi', 'mkv', '3gp'];
    return files.filter(f => {
      const ext = (f.extension || '').toLowerCase();
      return imageExts.includes(ext) || videoExts.includes(ext);
    });
  }

  function navigatePreview(direction) {
    if (!previewFile) return;
    const previewable = getPreviewableFiles();
    const currentIndex = previewable.findIndex(f => f.id === previewFile.id);
    if (currentIndex === -1) return;

    const newIndex = currentIndex + direction;
    if (newIndex >= 0 && newIndex < previewable.length) {
      previewFile = previewable[newIndex];
      previewLoading = true;
    }
  }

  function handleKeydown(e) {
    if (previewFile) {
      if (e.key === 'Escape') {
        closePreview();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        navigatePreview(-1);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        navigatePreview(1);
      }
    }
  }

  function isImage(ext) {
    return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif'].includes((ext || '').toLowerCase());
  }

  function isVideo(ext) {
    return ['mp4', 'mov', 'avi', 'mkv', '3gp'].includes((ext || '').toLowerCase());
  }

  onMount(loadFiles);
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="space-y-6">
  <h1 class="text-3xl font-bold">Files</h1>

  <div class="flex gap-4 items-center">
    <input
      type="text"
      bind:value={search}
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
            Path{getSortIcon('relative_path')}
          </th>
          <th class="px-4 py-3 text-right cursor-pointer hover:text-white select-none" on:click={() => toggleSort('size')}>
            Size{getSortIcon('size')}
          </th>
          <th class="px-4 py-3 cursor-pointer hover:text-white select-none" on:click={() => toggleSort('status')}>
            Status{getSortIcon('status')}
          </th>
          <th class="px-4 py-3 cursor-pointer hover:text-white select-none" on:click={() => toggleSort('mtime')}>
            Modified{getSortIcon('mtime')}
          </th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-700">
        {#each files as file}
          <tr
            class="hover:bg-gray-750 cursor-pointer"
            on:click={() => openPreview(file)}
          >
            <td class="px-4 py-3 font-mono text-xs truncate max-w-md" title={file.relative_path}>{file.relative_path}</td>
            <td class="px-4 py-3 text-right text-gray-400">{formatBytes(file.size)}</td>
            <td class="px-4 py-3">
              {#if file.status === 'error'}
                <span class="text-red-400">Error</span>
              {:else if file.media_id}
                <span class="text-green-400">Uploaded</span>
              {:else if file.sha256}
                <span class="text-blue-400">Hashed</span>
              {:else}
                <span class="text-gray-400">Pending</span>
              {/if}
            </td>
            <td class="px-4 py-3 text-gray-500">{formatDate(file.mtime)}</td>
          </tr>
        {:else}
          <tr>
            <td colspan="4" class="px-4 py-8 text-center text-gray-500">No files yet</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <div class="flex justify-between items-center">
    <button on:click={prevPage} disabled={page === 1} class="px-4 py-2 bg-gray-700 rounded disabled:opacity-50 hover:bg-gray-600">Previous</button>
    <span class="text-gray-400">Page {page} {total > 0 ? `(${total} total)` : ''}</span>
    <button on:click={nextPage} disabled={!hasMore} class="px-4 py-2 bg-gray-700 rounded disabled:opacity-50 hover:bg-gray-600">Next</button>
  </div>
</div>

<!-- Preview Modal -->
{#if previewFile}
  <div
    class="fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center z-50"
    on:click={closePreview}
  >
    <div
      class="relative max-w-4xl max-h-[90vh] bg-gray-900 rounded-lg overflow-hidden"
      on:click|stopPropagation
    >
      <!-- Close button -->
      <button
        class="absolute top-2 right-2 z-10 p-2 bg-gray-800 rounded-full hover:bg-gray-700 text-white"
        on:click={closePreview}
      >
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      <!-- File info header -->
      <div class="p-4 border-b border-gray-700">
        <p class="text-sm text-gray-400 truncate" title={previewFile.relative_path}>
          {previewFile.relative_path}
        </p>
        <p class="text-xs text-gray-500 mt-1">
          {formatBytes(previewFile.size)} · {previewFile.extension?.toUpperCase() || 'Unknown'}
        </p>
      </div>

      <!-- Media content -->
      <div class="flex items-center justify-center p-4 min-h-[300px]">
        {#if previewLoading}
          <div class="text-gray-400">Loading...</div>
        {/if}

        {#if isImage(previewFile.extension)}
          <img
            src="/api/files/{previewFile.id}/preview"
            alt={previewFile.filename}
            class="max-w-full max-h-[70vh] object-contain"
            on:load={() => previewLoading = false}
            on:error={() => previewLoading = false}
            class:hidden={previewLoading}
          />
        {:else if isVideo(previewFile.extension)}
          <video
            src="/api/files/{previewFile.id}/preview"
            controls
            class="max-w-full max-h-[70vh]"
            on:loadeddata={() => previewLoading = false}
            on:error={() => previewLoading = false}
            class:hidden={previewLoading}
          >
            Your browser does not support video playback.
          </video>
        {/if}
      </div>
    </div>
  </div>
{/if}
