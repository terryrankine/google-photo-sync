<script>
  export let queue = {};

  // Defensive defaults for nested properties
  $: hashQueue = {
    pending_batches: queue?.hash?.pending_batches ?? 0,
    running_batches: queue?.hash?.running_batches ?? 0,
    pending_files: queue?.hash?.pending_files ?? 0
  };
  $: uploadQueue = {
    pending_batches: queue?.upload?.pending_batches ?? 0,
    running_batches: queue?.upload?.running_batches ?? 0,
    pending_files: queue?.upload?.pending_files ?? 0
  };

  function formatNumber(n) {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toString();
  }
</script>

<div class="grid grid-cols-2 gap-4">
  <!-- Hash Queue -->
  <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
    <div class="text-sm text-gray-400 mb-2">Hash Queue</div>
    <div class="flex items-baseline space-x-2">
      <span class="text-2xl font-bold text-green-400">{hashQueue.running_batches}</span>
      <span class="text-gray-400 text-sm">running</span>
    </div>
    <div class="text-sm text-gray-500 mt-1">
      {hashQueue.pending_batches} pending
      {#if hashQueue.pending_files > 0}
        <span class="text-gray-600">({formatNumber(hashQueue.pending_files)} files)</span>
      {/if}
    </div>
    <div class="w-full bg-gray-700 rounded-full h-1.5 mt-3">
      {#if hashQueue.running_batches + hashQueue.pending_batches > 0}
        <div
          class="bg-green-500 h-1.5 rounded-full transition-all duration-300"
          style="width: {(hashQueue.running_batches / Math.max(hashQueue.running_batches + hashQueue.pending_batches, 1)) * 100}%"
        ></div>
      {/if}
    </div>
  </div>

  <!-- Upload Queue -->
  <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
    <div class="text-sm text-gray-400 mb-2">Upload Queue</div>
    <div class="flex items-baseline space-x-2">
      <span class="text-2xl font-bold text-blue-400">{uploadQueue.running_batches}</span>
      <span class="text-gray-400 text-sm">running</span>
    </div>
    <div class="text-sm text-gray-500 mt-1">
      {uploadQueue.pending_batches} pending
      {#if uploadQueue.pending_files > 0}
        <span class="text-gray-600">({formatNumber(uploadQueue.pending_files)} files)</span>
      {/if}
    </div>
    <div class="w-full bg-gray-700 rounded-full h-1.5 mt-3">
      {#if uploadQueue.running_batches + uploadQueue.pending_batches > 0}
        <div
          class="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
          style="width: {(uploadQueue.running_batches / Math.max(uploadQueue.running_batches + uploadQueue.pending_batches, 1)) * 100}%"
        ></div>
      {/if}
    </div>
  </div>
</div>
