<script>
  import { onMount } from 'svelte';
  import { api } from '../api.js';

  let sourceDirs = '';
  let fileExtensions = '.jpg,.jpeg,.png,.heic,.mp4,.mov';
  let ignorePatterns = '.thumbnails,@eaDir';
  let parallelUploads = 4;
  let parallelHashers = 4;
  let saving = false;
  let message = '';

  onMount(async () => {
    try {
      const data = await api.getConfig();
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
    } catch (e) {
      console.error(e);
    }
  });

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
