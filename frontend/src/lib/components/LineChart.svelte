<script>
  import { Chart, Svg, Axis, Spline, Highlight, Tooltip } from 'layerchart';
  import { scaleTime, scaleLinear } from 'd3-scale';
  import { format } from 'date-fns';

  export let data = { labels: [], datasets: [] };
  export let title = '';

  // Transform Chart.js format to LayerChart format
  $: chartData = data.labels.map((label, i) => {
    const point = { date: new Date(label) };
    data.datasets.forEach((ds, j) => {
      point[`series${j}`] = ds.data[i] || 0;
    });
    return point;
  });

  $: seriesKeys = data.datasets.map((_, i) => `series${i}`);
  $: seriesColors = data.datasets.map(ds => ds.borderColor || '#3b82f6');
  $: seriesLabels = data.datasets.map(ds => ds.label || `Series ${ds}`);
</script>

<div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
  {#if title}
    <h2 class="text-xl font-semibold mb-4">{title}</h2>
  {/if}

  <div class="h-64">
    {#if chartData.length > 0}
      <Chart
        data={chartData}
        x="date"
        xScale={scaleTime()}
        y={seriesKeys[0]}
        yScale={scaleLinear()}
        yDomain={[0, null]}
        padding={{ left: 40, bottom: 24, right: 16, top: 8 }}
      >
        <Svg>
          <Axis placement="left" grid={{ class: 'stroke-gray-700' }} tick={{ class: 'fill-gray-400' }} />
          <Axis placement="bottom" tick={{ class: 'fill-gray-400' }} format={(d) => format(d, 'MMM d')} />

          {#each seriesKeys as key, i}
            <Spline y={key} class="stroke-2" style="stroke: {seriesColors[i]}; fill: none;" />
          {/each}

          <Highlight area lines={{ class: 'stroke-gray-500' }} />
        </Svg>

        <Tooltip.Root header={(d) => format(d.date, 'MMM d, HH:mm')} let:data>
          {#each seriesKeys as key, i}
            <Tooltip.Item label={seriesLabels[i]} value={data[key]} />
          {/each}
        </Tooltip.Root>
      </Chart>
    {:else}
      <div class="h-full flex items-center justify-center text-gray-500">
        No data available
      </div>
    {/if}
  </div>

  <!-- Legend -->
  {#if data.datasets.length > 0}
    <div class="flex justify-center gap-6 mt-4">
      {#each data.datasets as ds, i}
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-full" style="background-color: {ds.borderColor}"></div>
          <span class="text-sm text-gray-400">{ds.label}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>
