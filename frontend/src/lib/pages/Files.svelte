<script>
  import { writable } from 'svelte/store';
  import { createQuery } from '@tanstack/svelte-query';
  import {
    createSvelteTable,
    getCoreRowModel,
    flexRender,
  } from '@tanstack/svelte-table';

  // Pagination & sorting state
  let pagination = { pageIndex: 0, pageSize: 50 };
  let sorting = [{ id: 'relative_path', desc: false }];
  let globalFilter = '';
  let statusFilter = '';
  let searchTimeout;

  // Preview modal state
  let previewFile = null;

  // Build query params from state
  $: queryParams = {
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
    search: globalFilter,
    status: statusFilter,
    sortBy: sorting[0]?.id || 'relative_path',
    sortDir: sorting[0]?.desc ? 'desc' : 'asc',
  };

  // Fetch files with createQuery
  const filesQuery = createQuery({
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

  // Column definitions
  const columns = [
    {
      accessorKey: 'relative_path',
      header: 'Path',
      cell: info => info.getValue(),
    },
    {
      accessorKey: 'size',
      header: 'Size',
      cell: info => formatBytes(info.getValue()),
    },
    {
      id: 'status',
      header: 'Status',
      cell: info => getStatus(info.row.original),
    },
    {
      accessorKey: 'mtime',
      header: 'Modified',
      cell: info => formatDate(info.getValue()),
    },
  ];

  // Table state handlers
  const setPagination = (updater) => {
    pagination = typeof updater === 'function' ? updater(pagination) : updater;
    options.update(old => ({ ...old, state: { ...old.state, pagination } }));
  };

  const setSorting = (updater) => {
    sorting = typeof updater === 'function' ? updater(sorting) : updater;
    pagination = { ...pagination, pageIndex: 0 }; // Reset to first page on sort
    options.update(old => ({ ...old, state: { ...old.state, sorting, pagination } }));
  };

  // Table options store
  const options = writable({
    data: [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    pageCount: 0,
  });

  // Update table data when query changes
  $: if ($filesQuery.data) {
    options.update(old => ({
      ...old,
      data: $filesQuery.data.files || [],
      pageCount: Math.ceil(($filesQuery.data.total || 0) / pagination.pageSize),
    }));
  }

  const table = createSvelteTable(options);

  // Search with debounce
  function handleSearch(e) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      globalFilter = e.target.value;
      pagination = { ...pagination, pageIndex: 0 };
      options.update(old => ({ ...old, state: { ...old.state, pagination } }));
    }, 300);
  }

  function handleFilter() {
    pagination = { ...pagination, pageIndex: 0 };
    options.update(old => ({ ...old, state: { ...old.state, pagination } }));
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
        {#each $table.getHeaderGroups() as headerGroup}
          <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-900">
            {#each headerGroup.headers as header}
              <th
                class="px-4 py-3 cursor-pointer hover:text-white select-none"
                on:click={header.column.getToggleSortingHandler()}
              >
                {#if !header.isPlaceholder}
                  <svelte:component this={flexRender(header.column.columnDef.header, header.getContext())} />
                  {#if header.column.getIsSorted() === 'asc'}
                    ▲
                  {:else if header.column.getIsSorted() === 'desc'}
                    ▼
                  {/if}
                {/if}
              </th>
            {/each}
          </tr>
        {/each}
      </thead>
      <tbody class="divide-y divide-gray-700">
        {#each $table.getRowModel().rows as row}
          <tr class="hover:bg-gray-750 cursor-pointer" on:click={() => openPreview(row.original)}>
            {#each row.getVisibleCells() as cell}
              <td class="px-4 py-3" class:font-mono={cell.column.id === 'relative_path'} class:text-xs={cell.column.id === 'relative_path'} class:truncate={cell.column.id === 'relative_path'} class:max-w-md={cell.column.id === 'relative_path'} class:text-right={cell.column.id === 'size'} class:text-gray-400={cell.column.id === 'size'} class:text-gray-500={cell.column.id === 'mtime'}>
                {#if cell.column.id === 'status'}
                  {@const status = getStatus(row.original)}
                  <span class={status.class}>{status.text}</span>
                {:else}
                  <svelte:component this={flexRender(cell.column.columnDef.cell, cell.getContext())} />
                {/if}
              </td>
            {/each}
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
      on:click={() => $table.previousPage()}
      disabled={!$table.getCanPreviousPage()}
      class="px-4 py-2 bg-gray-700 rounded disabled:opacity-50 hover:bg-gray-600"
    >
      Previous
    </button>
    <span class="text-gray-400">
      Page {pagination.pageIndex + 1} of {$table.getPageCount() || 1}
      {#if $filesQuery.data?.total}
        ({$filesQuery.data.total} total)
      {/if}
    </span>
    <button
      on:click={() => $table.nextPage()}
      disabled={!$table.getCanNextPage()}
      class="px-4 py-2 bg-gray-700 rounded disabled:opacity-50 hover:bg-gray-600"
    >
      Next
    </button>
  </div>
</div>

<!-- Preview Modal -->
{#if previewFile}
  <div class="fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center z-50" on:click={closePreview}>
    <div class="relative max-w-4xl max-h-[90vh] bg-gray-900 rounded-lg overflow-hidden" on:click|stopPropagation>
      <button class="absolute top-2 right-2 z-10 p-2 bg-gray-800 rounded-full hover:bg-gray-700 text-white" on:click={closePreview}>
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
            Your browser does not support video playback.
          </video>
        {/if}
      </div>
    </div>
  </div>
{/if}
