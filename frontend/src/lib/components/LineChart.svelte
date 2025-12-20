<script>
  import { onMount, onDestroy } from 'svelte';
  import Chart from 'chart.js/auto';

  export let data = { labels: [], datasets: [] };
  export let title = '';

  let canvas;
  let chart;

  $: if (chart && data) {
    chart.data = data;
    chart.update();
  }

  onMount(() => {
    chart = new Chart(canvas, {
      type: 'line',
      data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: '#9ca3af' }
          }
        },
        scales: {
          x: {
            ticks: { color: '#9ca3af' },
            grid: { color: '#374151' }
          },
          y: {
            ticks: { color: '#9ca3af' },
            grid: { color: '#374151' }
          }
        }
      }
    });
  });

  onDestroy(() => {
    if (chart) chart.destroy();
  });
</script>

<div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
  {#if title}
    <h2 class="text-xl font-semibold mb-4">{title}</h2>
  {/if}
  <div class="h-64">
    <canvas bind:this={canvas}></canvas>
  </div>
</div>
