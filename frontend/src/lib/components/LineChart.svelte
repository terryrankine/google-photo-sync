<script>
  let { data = { labels: [], datasets: [] }, title = '', yAxisLabel = 'files/5min' } = $props();

  // SVG dimensions
  const width = 800;
  const height = 240;
  const padding = { top: 20, right: 30, bottom: 45, left: 60 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Tooltip state
  let tooltipVisible = $state(false);
  let tooltipX = $state(0);
  let tooltipY = $state(0);
  let tooltipData = $state({ label: '', values: [] });
  let hoveredIndex = $state(-1);

  // Calculate max Y value for scaling
  let maxY = $derived(() => {
    let max = 0;
    data.datasets?.forEach(ds => {
      ds.data?.forEach(v => { if (v > max) max = v; });
    });
    return Math.max(max, 10); // Minimum 10 for better scaling
  });

  // Generate smooth curved path using monotone cubic interpolation
  function getCurvedPath(dataset) {
    if (!dataset?.data?.length || !data.labels?.length) return '';
    const points = dataset.data.map((val, i) => ({
      x: padding.left + (i / Math.max(data.labels.length - 1, 1)) * chartWidth,
      y: padding.top + chartHeight - (val / maxY()) * chartHeight
    }));

    if (points.length < 2) return '';

    // Monotone cubic spline interpolation
    let path = `M ${points[0].x},${points[0].y}`;

    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(0, i - 1)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(points.length - 1, i + 2)];

      // Calculate control points for smooth curve
      const tension = 0.3;
      const cp1x = p1.x + (p2.x - p0.x) * tension;
      const cp1y = p1.y + (p2.y - p0.y) * tension;
      const cp2x = p2.x - (p3.x - p1.x) * tension;
      const cp2y = p2.y - (p3.y - p1.y) * tension;

      path += ` C ${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`;
    }

    return path;
  }

  // Generate area path (curved line + close to bottom)
  function getAreaPath(dataset) {
    const linePath = getCurvedPath(dataset);
    if (!linePath) return '';

    const points = dataset.data.map((val, i) => ({
      x: padding.left + (i / Math.max(data.labels.length - 1, 1)) * chartWidth,
      y: padding.top + chartHeight - (val / maxY()) * chartHeight
    }));

    const lastX = points[points.length - 1]?.x || padding.left;
    const firstX = points[0]?.x || padding.left;
    const bottomY = padding.top + chartHeight;

    return `${linePath} L ${lastX},${bottomY} L ${firstX},${bottomY} Z`;
  }

  // Smart Y-axis ticks
  let yTicks = $derived(() => {
    const max = maxY();
    // Nice round numbers for ticks
    const magnitude = Math.pow(10, Math.floor(Math.log10(max)));
    let step = magnitude;
    if (max / step < 3) step = magnitude / 2;
    if (max / step < 3) step = magnitude / 4;

    const ticks = [];
    for (let v = 0; v <= max; v += step) {
      ticks.push(Math.round(v));
    }
    if (ticks[ticks.length - 1] < max) {
      ticks.push(Math.ceil(max / step) * step);
    }
    return ticks.slice(0, 6); // Max 6 ticks
  });

  // X-axis labels
  let xLabels = $derived(() => {
    if (!data.labels?.length) return [];
    const step = Math.max(1, Math.floor(data.labels.length / 6));
    return data.labels.map((label, i) => ({
      label,
      i,
      show: i % step === 0 || i === data.labels.length - 1
    }));
  });

  // Generate unique gradient IDs
  let gradientId = $derived(() => `area-gradient-${Math.random().toString(36).substr(2, 9)}`);

  // Handle mouse movement over chart
  function handleMouseMove(event) {
    const svg = event.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const svgWidth = rect.width;

    // Convert mouse position to data index
    const chartStartX = (padding.left / width) * svgWidth;
    const chartEndX = ((width - padding.right) / width) * svgWidth;
    const relativeX = (mouseX - chartStartX) / (chartEndX - chartStartX);

    if (relativeX < 0 || relativeX > 1 || !data.labels?.length) {
      tooltipVisible = false;
      hoveredIndex = -1;
      return;
    }

    const index = Math.round(relativeX * (data.labels.length - 1));
    if (index < 0 || index >= data.labels.length) {
      tooltipVisible = false;
      hoveredIndex = -1;
      return;
    }

    hoveredIndex = index;
    tooltipX = event.clientX;
    tooltipY = event.clientY;
    tooltipData = {
      label: data.labels[index],
      values: data.datasets.map(ds => ({
        name: ds.label,
        value: ds.data?.[index] ?? 0,
        color: ds.borderColor || '#3b82f6'
      }))
    };
    tooltipVisible = true;
  }

  function handleMouseLeave() {
    tooltipVisible = false;
    hoveredIndex = -1;
  }
</script>

<div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
  {#if title}
    <h2 class="text-xl font-semibold mb-4">{title}</h2>
  {/if}

  <div class="overflow-x-auto relative">
    {#if data.labels?.length > 0}
      <svg
        viewBox="0 0 {width} {height}"
        class="w-full cursor-crosshair"
        style="min-width: 400px; max-height: 280px;"
        onmousemove={handleMouseMove}
        onmouseleave={handleMouseLeave}
        role="img"
        aria-label="Activity chart"
      >
        <!-- Gradient definitions for area fills -->
        <defs>
          {#each data.datasets as ds, i}
            <linearGradient id="{gradientId()}-{i}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color={ds.borderColor || '#3b82f6'} stop-opacity="0.4" />
              <stop offset="100%" stop-color={ds.borderColor || '#3b82f6'} stop-opacity="0.05" />
            </linearGradient>
          {/each}
        </defs>

        <!-- Grid lines -->
        {#each yTicks() as tick}
          <line
            x1={padding.left}
            y1={padding.top + chartHeight - (tick / maxY()) * chartHeight}
            x2={width - padding.right}
            y2={padding.top + chartHeight - (tick / maxY()) * chartHeight}
            stroke="#374151"
            stroke-dasharray="4,4"
            stroke-opacity="0.5"
          />
        {/each}

        <!-- Y-axis label (rotated) -->
        <text
          x={15}
          y={padding.top + chartHeight / 2}
          class="fill-gray-500 text-xs"
          text-anchor="middle"
          transform="rotate(-90, 15, {padding.top + chartHeight / 2})"
        >{yAxisLabel}</text>

        <!-- Y-axis tick labels -->
        {#each yTicks() as tick}
          <text
            x={padding.left - 10}
            y={padding.top + chartHeight - (tick / maxY()) * chartHeight + 4}
            class="fill-gray-400 text-xs"
            text-anchor="end"
          >{tick}</text>
        {/each}

        <!-- X-axis labels -->
        {#each xLabels() as { label, i, show }}
          {#if show}
            <text
              x={padding.left + (i / Math.max(data.labels.length - 1, 1)) * chartWidth}
              y={height - 10}
              class="fill-gray-400 text-xs"
              text-anchor="middle"
            >{label}</text>
          {/if}
        {/each}

        <!-- Area fills (rendered first, behind lines) -->
        {#each data.datasets as ds, i}
          <path
            d={getAreaPath(ds)}
            fill="url(#{gradientId()}-{i})"
            stroke="none"
          />
        {/each}

        <!-- Curved lines -->
        {#each data.datasets as ds, i}
          <path
            d={getCurvedPath(ds)}
            fill="none"
            stroke={ds.borderColor || '#3b82f6'}
            stroke-width="2.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        {/each}

        <!-- Data points -->
        {#each data.datasets as ds, i}
          {#each ds.data as val, j}
            <circle
              cx={padding.left + (j / Math.max(data.labels.length - 1, 1)) * chartWidth}
              cy={padding.top + chartHeight - (val / maxY()) * chartHeight}
              r="3"
              fill={ds.borderColor || '#3b82f6'}
              stroke="#1f2937"
              stroke-width="1.5"
            />
          {/each}
        {/each}

        <!-- Axes -->
        <line
          x1={padding.left}
          y1={padding.top}
          x2={padding.left}
          y2={padding.top + chartHeight}
          stroke="#4b5563"
          stroke-width="1"
        />
        <line
          x1={padding.left}
          y1={padding.top + chartHeight}
          x2={width - padding.right}
          y2={padding.top + chartHeight}
          stroke="#4b5563"
          stroke-width="1"
        />

        <!-- Hover vertical line -->
        {#if hoveredIndex >= 0 && data.labels?.length > 0}
          <line
            x1={padding.left + (hoveredIndex / Math.max(data.labels.length - 1, 1)) * chartWidth}
            y1={padding.top}
            x2={padding.left + (hoveredIndex / Math.max(data.labels.length - 1, 1)) * chartWidth}
            y2={padding.top + chartHeight}
            stroke="#9ca3af"
            stroke-width="1"
            stroke-dasharray="4,4"
          />
          <!-- Highlighted points -->
          {#each data.datasets as ds, i}
            <circle
              cx={padding.left + (hoveredIndex / Math.max(data.labels.length - 1, 1)) * chartWidth}
              cy={padding.top + chartHeight - ((ds.data?.[hoveredIndex] ?? 0) / maxY()) * chartHeight}
              r="5"
              fill={ds.borderColor || '#3b82f6'}
              stroke="#fff"
              stroke-width="2"
            />
          {/each}
        {/if}
      </svg>

      <!-- Tooltip -->
      {#if tooltipVisible}
        <div
          class="fixed z-50 bg-gray-900 border border-gray-600 rounded-lg shadow-lg px-3 py-2 pointer-events-none"
          style="left: {tooltipX + 12}px; top: {tooltipY - 10}px; transform: translateY(-50%);"
        >
          <div class="text-xs font-semibold text-gray-300 mb-1">{tooltipData.label}</div>
          {#each tooltipData.values as item}
            <div class="flex items-center gap-2 text-xs">
              <span class="w-2 h-2 rounded-full" style="background-color: {item.color}"></span>
              <span class="text-gray-400">{item.name}:</span>
              <span class="font-mono text-white">{item.value}</span>
            </div>
          {/each}
        </div>
      {/if}
    {:else}
      <div class="h-48 flex items-center justify-center text-gray-500">
        No data available
      </div>
    {/if}
  </div>

  <!-- Legend -->
  {#if data.datasets?.length > 0}
    <div class="flex justify-center gap-6 mt-4">
      {#each data.datasets as ds}
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-full" style="background-color: {ds.borderColor}"></div>
          <span class="text-sm text-gray-400">{ds.label}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>
