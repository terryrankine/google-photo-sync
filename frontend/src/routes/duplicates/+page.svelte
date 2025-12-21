<script>
  import { createQuery } from '@tanstack/svelte-query';
  import { Copy, Trash2, ExternalLink, ChevronDown, ChevronRight } from 'lucide-svelte';

  let page = $state(1);
  let expandedGroups = $state(new Set());

  const duplicatesQuery = createQuery(() => ({
    queryKey: ['duplicates', page],
    queryFn: async () => {
      const res = await fetch(`/api/files/duplicates?page=${page}&limit=25`);
      if (!res.ok) throw new Error('Failed to fetch duplicates');
      return res.json();
    },
  }));

  let duplicates = $derived(duplicatesQuery.data || { groups: [], total_groups: 0, total_duplicate_files: 0, wasted_bytes: 0 });

  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function toggleGroup(sha256) {
    if (expandedGroups.has(sha256)) {
      expandedGroups.delete(sha256);
    } else {
      expandedGroups.add(sha256);
    }
    expandedGroups = new Set(expandedGroups); // trigger reactivity
  }

  function isExpanded(sha256) {
    return expandedGroups.has(sha256);
  }
</script>

<div class="space-y-6">
  <div class="flex justify-between items-center">
    <h1 class="text-3xl font-bold">Duplicate Files</h1>
  </div>

  <!-- Summary -->
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <div class="grid grid-cols-3 gap-6 text-center">
      <div>
        <Copy class="w-8 h-8 mx-auto mb-2 text-yellow-400" />
        <div class="text-3xl font-bold text-yellow-400">{duplicates.total_groups}</div>
        <div class="text-gray-400">Duplicate Groups</div>
      </div>
      <div>
        <Trash2 class="w-8 h-8 mx-auto mb-2 text-red-400" />
        <div class="text-3xl font-bold text-red-400">{duplicates.total_duplicate_files}</div>
        <div class="text-gray-400">Duplicate Files</div>
      </div>
      <div>
        <div class="text-3xl font-bold text-orange-400">{formatBytes(duplicates.wasted_bytes)}</div>
        <div class="text-gray-400 mt-2">Wasted Space</div>
      </div>
    </div>
  </div>

  <!-- Help text -->
  <div class="bg-blue-900/30 border border-blue-700 rounded-lg p-4 text-sm text-blue-200">
    <p>
      Files with the same SHA256 hash are exact duplicates.
      Click a group to see all duplicate files.
      Consider keeping only one copy of each file to save storage space.
    </p>
  </div>

  <!-- Duplicates list -->
  <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
    {#if duplicatesQuery.isLoading}
      <div class="p-8 text-center text-gray-400">Loading duplicates...</div>
    {:else if duplicatesQuery.error}
      <div class="p-8 text-center text-red-400">Error: {duplicatesQuery.error.message}</div>
    {:else if duplicates.groups?.length === 0}
      <div class="p-8 text-center text-gray-400">No duplicate files found</div>
    {:else}
      <div class="divide-y divide-gray-700">
        {#each duplicates.groups as group}
          <div>
            <!-- Group header -->
            <button
              class="w-full px-4 py-3 flex items-center gap-3 hover:bg-gray-700/50 text-left"
              onclick={() => toggleGroup(group.sha256)}
            >
              {#if isExpanded(group.sha256)}
                <ChevronDown class="w-5 h-5 text-gray-400" />
              {:else}
                <ChevronRight class="w-5 h-5 text-gray-400" />
              {/if}
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="font-mono text-xs text-gray-500">{group.sha256.slice(0, 16)}...</span>
                  <span class="px-2 py-0.5 bg-yellow-900/50 text-yellow-400 text-xs rounded">
                    {group.count} copies
                  </span>
                </div>
              </div>
              <div class="text-sm text-gray-400">
                {formatBytes(group.total_size)} total
              </div>
            </button>

            <!-- Expanded file list -->
            {#if isExpanded(group.sha256)}
              <div class="bg-gray-900/50 border-t border-gray-700">
                {#each group.files as file}
                  <div class="px-8 py-2 flex items-center gap-4 text-sm hover:bg-gray-700/30 border-b border-gray-700/50 last:border-0">
                    <div class="flex-1 min-w-0">
                      <div class="truncate text-gray-300" title={file.relative_path}>
                        {file.relative_path}
                      </div>
                      <div class="text-xs text-gray-500">
                        {file.source_name} • {formatBytes(file.size)}
                      </div>
                    </div>
                    {#if file.media_id}
                      <a
                        href="https://photos.google.com/lr/photo/{file.media_id}"
                        target="_blank"
                        class="text-blue-400 hover:text-blue-300"
                        title="View in Google Photos"
                      >
                        <ExternalLink class="w-4 h-4" />
                      </a>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>

      <!-- Pagination -->
      {#if duplicates.total_groups > 25}
        <div class="px-4 py-3 border-t border-gray-700 flex justify-between items-center">
          <button
            class="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={page === 1}
            onclick={() => page--}
          >
            Previous
          </button>
          <span class="text-sm text-gray-400">
            Page {page} of {Math.ceil(duplicates.total_groups / 25)}
          </span>
          <button
            class="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={page * 25 >= duplicates.total_groups}
            onclick={() => page++}
          >
            Next
          </button>
        </div>
      {/if}
    {/if}
  </div>
</div>
