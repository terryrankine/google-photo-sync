<script>
  let { workers = [], title = "Workers", totalThroughput = 0, totalFilesPerSec = 0 } = $props();

  // HSL color interpolation: red (0) -> yellow (60) -> green (120)
  // Maps 0-100% to hue 0-120 for a smooth spectrum
  function getProgressColor(percent) {
    // Clamp to 0-100
    const p = Math.max(0, Math.min(100, percent));
    // Map percent to hue: 0% = red (0°), 50% = yellow (60°), 100% = green (120°)
    const hue = Math.round((p / 100) * 120);
    return `hsl(${hue}, 70%, 45%)`;
  }

  function formatSpeed(mbps) {
    if (mbps >= 1000) return `${(mbps / 1000).toFixed(1)} GB/s`;
    if (mbps >= 1) return `${mbps.toFixed(1)} MB/s`;
    return `${(mbps * 1024).toFixed(0)} KB/s`;
  }
</script>

<div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
  <div class="flex justify-between items-center mb-4">
    <h3 class="text-lg font-semibold text-white">{title}</h3>
    <div class="text-sm text-gray-400">
      {#if totalThroughput > 0}
        <span class="text-green-400 font-mono">{formatSpeed(totalThroughput)}</span>
        <span class="mx-2">|</span>
      {/if}
      <span class="font-mono">{totalFilesPerSec.toFixed(1)} files/s</span>
    </div>
  </div>

  {#if workers.length === 0}
    <div class="text-gray-500 text-sm py-4 text-center">No workers active</div>
  {:else}
    <div class="space-y-3">
      {#each workers as worker}
        <div class="bg-gray-700/50 rounded-lg p-3">
          <div class="flex justify-between items-center mb-2">
            <span class="text-sm font-medium text-white">
              Worker {worker.worker_id}
              {#if worker.idle}
                <span class="text-gray-500 text-xs ml-2">Idle</span>
              {:else}
                <span class="text-gray-400 text-xs ml-2">
                  Batch #{worker.batch_id}
                </span>
              {/if}
            </span>
            {#if !worker.idle}
              <span class="text-xs font-mono text-green-400">
                {formatSpeed(worker.throughput_mbps)}
              </span>
            {/if}
          </div>

          {#if !worker.idle}
            <div class="w-full bg-gray-600 rounded-full h-2 mb-1">
              <div
                class="h-2 rounded-full transition-all duration-300"
                style="width: {worker.progress_percent}%; background-color: {getProgressColor(worker.progress_percent)}"
              ></div>
            </div>
            <div class="flex justify-between text-xs text-gray-400">
              <span>{worker.files_processed}/{worker.files_total} files</span>
              <span>{worker.files_per_second.toFixed(1)} files/s</span>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>
