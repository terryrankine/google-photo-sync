<script>
  let { title = '', value = 0, subtitle = '', color = 'blue' } = $props();
</script>

<div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
  <div class="text-gray-400 text-sm font-medium">{title}</div>
  <div class="mt-2 text-2xl font-bold">{value}</div>
  {#if subtitle}
    <div class="text-sm text-gray-500">{subtitle}</div>
  {/if}
</div>
