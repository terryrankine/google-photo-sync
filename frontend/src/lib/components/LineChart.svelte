<script>
  import { onMount, onDestroy } from 'svelte';
  import Chart from 'chart.js/auto';

  export let data = { labels: [], datasets: [] };
  export let title = '';
  export let dualAxis = false;

  let canvas;
  let chart;

  // Assign datasets to axes when dualAxis is enabled
  function prepareData(inputData) {
    if (!dualAxis || !inputData.datasets) return inputData;

    return {
      ...inputData,
      datasets: inputData.datasets.map((ds, i) => ({
        ...ds,
        yAxisID: i === 1 ? 'y1' : 'y'  // Second dataset (Hashed) on right axis
      }))
    };
  }

  $: if (chart && data) {
    chart.data = prepareData(data);
    chart.update('none');
  }

  onMount(() => {
    const scales = {
      x: {
        ticks: { color: '#9ca3af' },
        grid: { color: '#374151' }
      },
      y: {
        type: 'linear',
        position: 'left',
        ticks: { color: '#3b82f6' },  // Blue for uploaded
        grid: { color: '#374151' },
        title: dualAxis ? { display: true, text: 'Uploaded / Errors', color: '#9ca3af' } : {}
      }
    };

    if (dualAxis) {
      scales.y1 = {
        type: 'linear',
        position: 'right',
        ticks: { color: '#10b981' },  // Green for hashed
        grid: { drawOnChartArea: false },
        title: { display: true, text: 'Hashed', color: '#9ca3af' }
      };
    }

    chart = new Chart(canvas, {
      type: 'line',
      data: prepareData(data),
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            labels: { color: '#9ca3af' }
          }
        },
        scales
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
