<script>
  import { onMount } from 'svelte';
  import { api } from '../api.js';
  import { jobs as jobsStore, jobsLoaded, loadJobs as loadJobsStore } from '../stores/jobs.js';

  let deleting = {};

  // Subscribe to store
  $: jobs = $jobsStore;

  function formatDate(ts) {
    return new Date(ts).toLocaleString();
  }

  async function refreshJobs() {
    await loadJobsStore(50);
  }

  async function deleteJob(id) {
    if (!confirm(`Delete job ${id}?`)) return;

    deleting[id] = true;
    try {
      await api.deleteJob(id);
      await refreshJobs();
    } catch (e) {
      console.error(e);
      alert('Failed to delete job: ' + e.message);
    }
    deleting[id] = false;
  }

  async function clearFinished() {
    if (!confirm('Delete all completed and failed jobs?')) return;

    try {
      const result = await api.cleanupJobs(0, 'all');
      await refreshJobs();
      alert(`Deleted ${result.deleted} jobs`);
    } catch (e) {
      console.error(e);
      alert('Failed to clear jobs: ' + e.message);
    }
  }

  function isActiveJob(status) {
    return ['running', 'scanning', 'hashing', 'uploading', 'paused'].includes(status);
  }

  onMount(() => {
    // Only fetch if not already loaded by App.svelte preload
    if (!$jobsLoaded) {
      refreshJobs();
    }
  });
</script>

<div class="space-y-6">
  <div class="flex justify-between items-center">
    <h1 class="text-3xl font-bold">Sync Jobs</h1>
    <button
      on:click={clearFinished}
      class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
    >
      Clear Finished
    </button>
  </div>

  <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-900">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">Status</th>
          <th class="px-4 py-3">Phase</th>
          <th class="px-4 py-3">Started</th>
          <th class="px-4 py-3 text-right">Scanned</th>
          <th class="px-4 py-3 text-right">Hashed</th>
          <th class="px-4 py-3 text-right">Uploaded</th>
          <th class="px-4 py-3 text-right">Errors</th>
          <th class="px-4 py-3 w-16"></th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-700">
        {#each jobs as job}
          <tr class="hover:bg-gray-750">
            <td class="px-4 py-3 font-medium">{job.id}</td>
            <td class="px-4 py-3">
              <span class="px-2 py-1 rounded text-xs"
                class:bg-green-900={job.status === 'completed'}
                class:text-green-300={job.status === 'completed'}
                class:bg-blue-900={job.status === 'running'}
                class:text-blue-300={job.status === 'running'}
                class:bg-yellow-900={job.status === 'paused'}
                class:text-yellow-300={job.status === 'paused'}
                class:bg-red-900={job.status === 'failed'}
                class:text-red-300={job.status === 'failed'}
              >
                {job.status}
              </span>
            </td>
            <td class="px-4 py-3 text-gray-400">{job.current_phase || '-'}</td>
            <td class="px-4 py-3 text-gray-400">{formatDate(job.started_at)}</td>
            <td class="px-4 py-3 text-right">{job.files_scanned || 0}</td>
            <td class="px-4 py-3 text-right">{job.files_hashed || 0}</td>
            <td class="px-4 py-3 text-right">{job.files_uploaded || 0}</td>
            <td class="px-4 py-3 text-right text-red-400">{job.files_errored || 0}</td>
            <td class="px-4 py-3 text-center">
              {#if !isActiveJob(job.status)}
                <button
                  on:click|stopPropagation={() => deleteJob(job.id)}
                  disabled={deleting[job.id]}
                  class="p-1 text-gray-400 hover:text-red-400 disabled:opacity-50"
                  title="Delete job"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              {/if}
            </td>
          </tr>
        {:else}
          <tr>
            <td colspan="9" class="px-4 py-8 text-center text-gray-500">No jobs yet. Start a sync from the Dashboard.</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>
