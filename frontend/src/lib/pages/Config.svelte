<script>
  import { onMount } from 'svelte';
  import { api } from '../api.js';
  import { config as configStore, authStatus as authStatusStore, configLoaded, loadAllConfig, loadAuthStatus } from '../stores/config.js';

  let sourceDirs = '';
  let fileExtensions = '.jpg,.jpeg,.png,.heic,.mp4,.mov';
  let ignorePatterns = '.thumbnails,@eaDir';
  let parallelUploads = 4;
  let parallelHashers = 4;
  let saving = false;
  let message = '';

  // Auth state (local UI state, not from store)
  let authUrl = '';
  let authCode = '';
  let authMessage = '';
  let authLoading = false;

  // Subscribe to auth status from store
  $: authStatus = $authStatusStore;

  function applyConfig(data) {
    // Parse source_dirs from JSON array to newline-separated string
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

  onMount(async () => {
    // Use preloaded config from store if available
    if ($configLoaded) {
      applyConfig($configStore);
    } else {
      await loadAllConfig();
      applyConfig($configStore);
    }
  });

  async function startReauth() {
    authLoading = true;
    authMessage = '';
    try {
      const data = await api.getAuthUrl();
      authUrl = data.url;
    } catch (e) {
      authMessage = e.message || 'Failed to get auth URL';
    }
    authLoading = false;
  }

  async function submitCode() {
    if (!authCode.trim()) return;
    authLoading = true;
    authMessage = '';
    try {
      await api.submitAuthCode(authCode.trim());
      authMessage = 'Authentication successful!';
      authUrl = '';
      authCode = '';
      await loadAuthStatus();  // Update store
    } catch (e) {
      authMessage = e.message || 'Failed to authenticate';
    }
    authLoading = false;
  }

  async function revokeAuth() {
    if (!confirm('This will delete your authentication token. You will need to re-authenticate to sync.')) return;
    authLoading = true;
    try {
      await api.revokeAuth();
      await loadAuthStatus();  // Update store
      authMessage = 'Token revoked. Click "Re-authenticate" to sign in again.';
    } catch (e) {
      authMessage = e.message || 'Failed to revoke';
    }
    authLoading = false;
  }

  async function save() {
    saving = true;
    message = '';
    try {
      // Convert newline-separated dirs back to array for storage
      const dirsArray = sourceDirs.split('\n').map(d => d.trim()).filter(d => d);

      // Save config settings
      await api.updateConfig({
        file_extensions: fileExtensions,
        ignore_patterns: ignorePatterns,
        parallel_uploads: parallelUploads,
        parallel_hashers: parallelHashers
      });

      // Save source directories
      await api.updateSourceDirs(dirsArray);

      message = 'Settings saved!';
    } catch (e) {
      message = 'Error saving settings';
      console.error(e);
    }
    saving = false;
  }
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
          <input
            type="text"
            bind:value={authCode}
            placeholder="Paste authorization code"
            class="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white text-sm"
          />
          <button
            on:click={submitCode}
            disabled={authLoading || !authCode.trim()}
            class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded font-medium text-sm disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      </div>
    {:else if authStatus?.has_credentials}
      <div class="flex space-x-3">
        <button
          on:click={startReauth}
          disabled={authLoading}
          class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium text-sm disabled:opacity-50"
        >
          {authLoading ? 'Loading...' : 'Re-authenticate'}
        </button>
        {#if authStatus?.status === 'authenticated'}
          <button
            on:click={revokeAuth}
            disabled={authLoading}
            class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded font-medium text-sm disabled:opacity-50"
          >
            Revoke Token
          </button>
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
      <label class="block text-sm font-medium text-gray-400 mb-2">Source Directories</label>
      <textarea
        bind:value={sourceDirs}
        class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white"
        rows="3"
        placeholder="/photos&#10;/media/photos"
      ></textarea>
      <p class="text-xs text-gray-500 mt-1">One directory per line</p>
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-400 mb-2">File Extensions</label>
      <input
        type="text"
        bind:value={fileExtensions}
        class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white"
      />
      <p class="text-xs text-gray-500 mt-1">Comma-separated list</p>
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-400 mb-2">Ignore Patterns</label>
      <input
        type="text"
        bind:value={ignorePatterns}
        class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white"
      />
      <p class="text-xs text-gray-500 mt-1">Comma-separated patterns to skip</p>
    </div>

    <div class="grid grid-cols-2 gap-4">
      <div>
        <label class="block text-sm font-medium text-gray-400 mb-2">Upload Workers</label>
        <input
          type="number"
          bind:value={parallelUploads}
          min="1" max="8"
          class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white"
        />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-400 mb-2">Hash Workers</label>
        <input
          type="number"
          bind:value={parallelHashers}
          min="1" max="8"
          class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white"
        />
      </div>
    </div>

    <div class="flex items-center justify-between pt-4 border-t border-gray-700">
      <button
        on:click={save}
        disabled={saving}
        class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
      >
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
      {#if message}
        <span class:text-green-400={message.includes('saved')} class:text-red-400={message.includes('Error')}>{message}</span>
      {/if}
    </div>
  </div>
</div>
