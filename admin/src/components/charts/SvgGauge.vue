<template>
  <div class="svg-gauge" :style="{ height: height + 'px' }">
    <svg :viewBox="'0 0 140 140'" style="width: 100%; height: 100%;">
      <!-- Background ring -->
      <circle cx="70" cy="70" :r="radius" fill="none" stroke="var(--gauge-bg, #e6e6e6)" :stroke-width="strokeWidth" />
      <!-- Progress ring -->
      <circle
        cx="70" cy="70" :r="radius" fill="none"
        :stroke="gaugeColor" :stroke-width="strokeWidth"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="dashOffset"
        stroke-linecap="round"
        transform="rotate(-90 70 70)"
        style="transition: stroke-dashoffset 0.6s ease, stroke 0.3s ease;"
      />
      <!-- Center text -->
      <text x="70" y="68" text-anchor="middle" :fill="gaugeColor" style="font-size: 26px; font-weight: 700;">
        {{ Math.round(value) }}%
      </text>
      <text x="70" y="88" text-anchor="middle" fill="var(--text-color-secondary, #999)" style="font-size: 11px;">
        {{ label }}
      </text>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  value: number
  label?: string
  height?: number
}>(), {
  label: '',
  height: 180,
})

const strokeWidth = 10
const radius = 55
const circumference = 2 * Math.PI * radius

const dashOffset = computed(() => {
  const pct = Math.min(Math.max(props.value, 0), 100)
  return circumference * (1 - pct / 100)
})

const gaugeColor = computed(() => {
  const v = props.value
  if (v > 85) return '#ff4d4f'
  if (v > 70) return '#faad14'
  return '#52c41a'
})
</script>

<style scoped>
.svg-gauge { display: flex; justify-content: center; align-items: center; }
</style>
