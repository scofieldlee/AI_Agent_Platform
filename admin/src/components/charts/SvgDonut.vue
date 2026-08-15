<template>
  <div class="svg-donut" :style="{ height: height + 'px' }">
    <svg :viewBox="'0 0 200 200'" style="width: 100%; height: 100%;">
      <!-- Background ring -->
      <circle cx="100" cy="100" :r="outerR" fill="none" stroke="var(--donut-bg, #f0f0f0)" :stroke-width="ringWidth" />
      <!-- Slices -->
      <template v-if="total > 0">
        <path
          v-for="(slice, i) in slices"
          :key="i"
          :d="slice.path"
          :fill="slice.color"
          :stroke="'var(--card-bg, #fff)'"
          :stroke-width="1.5"
          style="transition: opacity 0.2s ease;"
          @mouseenter="hovered = i"
          @mouseleave="hovered = -1"
          :opacity="hovered === -1 || hovered === i ? 1 : 0.5"
        />
      </template>
      <!-- Center text -->
      <text x="100" y="95" text-anchor="middle" fill="var(--text-color, #333)" style="font-size: 24px; font-weight: 700;">
        {{ total }}
      </text>
      <text x="100" y="115" text-anchor="middle" fill="var(--text-color-secondary, #999)" style="font-size: 11px;">
        总计
      </text>
      <!-- Hover tooltip -->
      <text v-if="hovered >= 0 && slices[hovered]" x="100" y="135" text-anchor="middle" :fill="slices[hovered].color" style="font-size: 12px; font-weight: 600;">
        {{ slices[hovered].label }}: {{ slices[hovered].value }}
      </text>
    </svg>
    <!-- Legend -->
    <div class="donut-legend">
      <div v-for="(slice, i) in slices" :key="i" class="legend-item">
        <span class="legend-dot" :style="{ background: slice.color }"></span>
        <span class="legend-label">{{ slice.label }}</span>
        <span class="legend-value">{{ slice.value }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface DonutItem {
  label: string
  value: number
  color: string
}

const props = withDefaults(defineProps<{
  data: DonutItem[]
  height?: number
}>(), {
  height: 200,
})

const hovered = ref(-1)
const cx = 100, cy = 100
const outerR = 65, innerR = 40
const ringWidth = outerR - innerR
const midR = (outerR + innerR) / 2

const total = computed(() => props.data.reduce((s, d) => s + d.value, 0))

const slices = computed(() => {
  if (total.value === 0) return []
  let currentAngle = -Math.PI / 2 // start from top
  return props.data.map(item => {
    const angle = (item.value / total.value) * 2 * Math.PI
    const startAngle = currentAngle
    const endAngle = currentAngle + angle

    // Donut slice path (annular sector)
    const x1 = cx + midR * Math.cos(startAngle)
    const y1 = cy + midR * Math.sin(startAngle)
    const x2 = cx + midR * Math.cos(endAngle)
    const y2 = cy + midR * Math.sin(endAngle)

    const largeArc = angle > Math.PI ? 1 : 0

    // Outer arc
    const x1o = cx + outerR * Math.cos(startAngle)
    const y1o = cy + outerR * Math.sin(startAngle)
    const x2o = cx + outerR * Math.cos(endAngle)
    const y2o = cy + outerR * Math.sin(endAngle)

    // Inner arc
    const x1i = cx + innerR * Math.cos(startAngle)
    const y1i = cy + innerR * Math.sin(startAngle)
    const x2i = cx + innerR * Math.cos(endAngle)
    const y2i = cy + innerR * Math.sin(endAngle)

    const path = [
      `M ${x1o} ${y1o}`,
      `A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2o} ${y2o}`,
      `L ${x2i} ${y2i}`,
      `A ${innerR} ${innerR} 0 ${largeArc} 0 ${x1i} ${y1i}`,
      'Z',
    ].join(' ')

    currentAngle = endAngle
    return { path, color: item.color, label: item.label, value: item.value }
  })
})
</script>

<style scoped>
.svg-donut { display: flex; align-items: center; gap: 16px; }
.donut-legend { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 0; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.legend-label { color: var(--text-color-secondary, #999); }
.legend-value { font-weight: 600; margin-left: auto; }
</style>
