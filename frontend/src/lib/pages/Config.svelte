<script>
  import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';

  const queryClient = useQueryClient();

  // Form state
  let sourceDirs = '';
  let fileExtensions = '.jpg,.jpeg,.png,.heic,.mp4,.mov';
  let ignorePatterns = '.thumbnails,@eaDir';
  let parallelUploads = 4;
  let parallelHashers = 4;
  let message = '';

  // Auth UI state
  let authUrl = '';
  let authCode = '';
  let authMessage = '';

  // Config query
  const configQuery = createQuery({
    queryKey: ['config'],
    queryFn: async () => {
      const res = await fetch('/api/config');
      if (!res.ok) throw new Error('Failed to fetch config');
      return res.json();
    },
  });

  // Auth status query
  const authQuery = createQuery({
    queryKey: ['auth', 'status'],
    queryFn: async () => {
      const res = await fetch('/api/auth/status');
      if (!res.ok) throw new Error('Failed to fetch auth status');
      return res.json();
    },
  });

  // Apply config when loaded
  $: if ($configQuery.data) {
    const data = $configQuery.data;
    if (data.source_dirs) {
      try {
        const dirs = JSON.parse(data.source_dirs);
        sourceDirs = Array.isArray(dirs) ? dirs.join('\n') : data.source_dirs;
      } catch {
        sourceDirs = data.source_dirs;
      }
    }
    fileExtensions = data.file_extensions || fileExtensions;
    ignorePatterns = data.ignore_patterns || ignorePatterns;
    parallelUploads = parseInt(data.parallel_uploads) || 4;
    parallelHashers = parseInt(data.parallel_hashers) || 4;
  }

  $: authStatus = $authQuery.data;

  // Save config mutation
  const saveMutation = createMutation({
    mutationFn: async () => {
      const dirsArray = sourceDirs.split('\n').map(d => d.trim()).filter(d => d);

      const configRes = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_extensions: fileExtensions,
          ignore_patterns: ignorePatterns,
          parallel_uploads: parallelUploads,
          parallel_hashers: parallelHashers
        })
      });
      if (!configRes.ok) throw new Error('Failed to save config');

      const dirsRes = await fetch('/api/config/source-dirs', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dirs: dirsArray })
      });
      if (!dirsRes.ok) throw new Error('Failed to save source dirs');
    },
    onSuccess: () => {
      message = 'Settings saved!';
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
    onError: () => {
      message = 'Error saving settings';
    },
  });

  // Auth mutations
  const getAuthUrlMutation = createMutation({
    mutationFn: async () => {
      const res = await fetch('/api/auth/url');
      if (!res.ok) throw new Error('Failed to get auth URL');
      return res.json();
    },
    onSuccess: (data) => {
      authUrl = data.url;
      authMessage = '';
    },
    onError: (e) => {
      authMessage = e.message || 'Failed to get auth URL';
    },
  });

  const submitCodeMutation = createMutation({
    mutationFn: async (code) => {
      const res = await fetch('/api/auth/callback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });
      if (!res.ok) throw new Error('Failed to authenticate');
      return res.json();
    },
    onSuccess: () => {
      authMessage = 'Authentication successful!';
      authUrl = '';
      authCode = '';
      queryClient.invalidateQueries({ queryKey: ['auth'] });
    },
    onError: (e) => {
      authMessage = e.message || 'Failed to authenticate';
    },
  });

  const revokeMutation = createMutation({
    mutationFn: async () => {
      const res = await fetch('/api/auth/revoke', { method: 'POST' });
      if (!res.ok) throw new Error('Failed to revoke');
      return res.json();
    },
    onSuccess: () => {
      authMessage = 'Token revoked. Click "Re-authenticate" to sign in again.';
      queryClient.invalidateQueries({ queryKey: ['auth'] });
    },
    onError: (e) => {
      authMessage = e.message || 'Failed to revoke';
    },
  });

  function startReauth() {
    authMessage = '';
    $getAuthUrlMutation.mutate();
  }

  function submitCode() {
    if (!authCode.trim()) return;
    $submitCodeMutation.mutate(authCode.trim());
  }

  function revokeAuth() {
    if (!confirm('This will delete your authentication token. You will need to re-authenticate to sync.')) return;
    $revokeMutation.mutate();
  }

  $: isAuthLoading = $getAuthUrlMutation.isPending || $submitCodeMutation.isPending || $revokeMutation.isPending;
</script>

<div class="space-y-6 max-w-2xl">
  <h1 class="text-3xl font-bold">Settings</h1>

  <!-- Authentication Section -->
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700 space-y-4">
    <h2 class="text-xl font-semibold">Google Photos Authentication</h2>

    {#if authStatus}
      <div class="flex items-center space-x-3">
        <span class="w-3 h-3 rounded-full" class:bg-green-500={authStatus.status === 'authenticated'} class:bg-yellow-500={authStatus.status === 'needs_auth'} class:bg-red-500={authStatus.status === 'needs_credentials'}></span>
        <span class="text-gray-300">
          {#if authStatus.status === 'authenticated'}
            Authenticated
          {:else if authStatus.status === 'needs_auth'}
            Token expired or missing - re-authentication required
          {:else}
            No credentials found - add client_id.json to /config
          {/if}
        </span>
      </div>
    {/if}

    {#if authUrl}
      <div class="space-y-3 p-4 bg-gray-900 rounded-lg">
        <p class="text-sm text-gray-400">1. Click the link below to authorize with Google:</p>
        <a href={authUrl} target="_blank" class="text-blue-400 hover:text-blue-300 underline break-all text-sm">{authUrl.slice(0, 80)}...</a>
        <p class="text-sm text-gray-400 mt-3">2. After authorizing, paste the code here:</p>
        <div class="flex space-x-2">
          <input type="text" bind:value={authCode} placeholder="Paste authorization code" class="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white text-sm" />
          <button on:click={submitCode} disabled={isAuthLoading || !authCode.trim()} class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded font-medium text-sm disabled:opacity-50">Submit</button>
        </div>
      </div>
    {:else if authStatus?.has_credentials}
      <div class="flex space-x-3">
        <button on:click={startReauth} disabled={isAuthLoading} class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium text-sm disabled:opacity-50">
          {isAuthLoading ? 'Loading...' : 'Re-authenticate'}
        </button>
        {#if authStatus?.status === 'authenticated'}
          <button on:click={revokeAuth} disabled={isAuthLoading} class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded font-medium text-sm disabled:opacity-50">Revoke Token</button>
        {/if}
      </div>
    {/if}

    {#if authMessage}
      <p class:text-green-400={authMessage.includes('successful')} class:text-red-400={!authMessage.includes('successful')} class="text-sm">{authMessage}</p>
    {/if}
  </div>

  <!-- Sync Settings -->
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700 space-y-6">
    <div>
      <label for="sourceDirs" class="block text-sm font-medium text-gray-400 mb-2">Source Directories</label>
      <textarea id="sourceDirs" bind:value={sourceDirs} class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white" rows="3" placeholder="/photos&#10;/media/photos"></textarea>
      <p class="text-xs text-gray-500 mt-1">One directory per line</p>
    </div>

    <div>
      <label for="fileExtensions" class="block text-sm font-medium text-gray-400 mb-2">File Extensions</label>
      <input id="fileExtensions" type="text" bind:value={fileExtensions} class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white" />
      <p class="text-xs text-gray-500 mt-1">Comma-separated list</p>
    </div>

    <div>
      <label for="ignorePatterns" class="block text-sm font-medium text-gray-400 mb-2">Ignore Patterns</label>
      <input id="ignorePatterns" type="text" bind:value={ignorePatterns} class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white" />
      <p class="text-xs text-gray-500 mt-1">Comma-separated patterns to skip</p>
    </div>

    <div class="grid grid-cols-2 gap-4">
      <div>
        <label for="parallelUploads" class="block text-sm font-medium text-gray-400 mb-2">Upload Workers</label>
        <input id="parallelUploads" type="number" bind:value={parallelUploads} min="1" max="8" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white" />
      </div>
      <div>
        <label for="parallelHashers" class="block text-sm font-medium text-gray-400 mb-2">Hash Workers</label>
        <input id="parallelHashers" type="number" bind:value={parallelHashers} min="1" max="8" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white" />
      </div>
    </div>

    <div class="flex items-center justify-between pt-4 border-t border-gray-700">
      <button on:click={() => $saveMutation.mutate()} disabled={$saveMutation.isPending} class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50">
        {$saveMutation.isPending ? 'Saving...' : 'Save Settings'}
      </button>
      {#if message}
        <span class:text-green-400={message.includes('saved')} class:text-red-400={message.includes('Error')}>{message}</span>
      {/if}
    </div>
  </div>
</div>
