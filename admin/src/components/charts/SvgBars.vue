<template>
  <div class="svg-bars" :style="{ height: height + 'px' }">
    <div v-if="data.length === 0" class="empty-bars">
      <span>暂无数据</span>
    </div>
    <div v-else class="bars-container">
      <div v-for="item in normalizedData" :key="item.label" class="bar-row">
        <div class="bar-label">{{ item.label }}</div>
        <div class="bar-track">
          <div
            class="bar-fill"
            :style="{
              width: item.percent + '%',
              background: item.color,
              borderRadius: '4px',
            }"
          >
            <span class="bar-value">{{ item.value }}ms</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface BarItem {
  label: string
  value: number
  color: string
}

const props = withDefaults(defineProps<{
  data: BarItem[]
  height?: number
}>(), {
  height: 200,
})

const maxValue = computed(() => {
  if (props.data.length === 0) return 1
  return Math.max(...props.data.map(d => d.value), 1)
})

const normalizedData = computed(() => {
  return props.data.map(item => ({
    ...item,
    percent: Math.max((item.value / maxValue.value) * 100, 3), // min 3% for visibility
  }))
})
</script>

<style scoped>
.svg-bars { display: flex; flex-direction: column; justify-content: center; }
.empty-bars { display: flex; justify-content: center; align-items: center; height: 100%; color: var(--text-color-secondary, #999); }
.bars-container { display: flex; flex-direction: column; gap: 16px; }
.bar-row { display: flex; align-items: center; gap: 12px; }
.bar-label {
  width: 70px; font-size: 13px; font-weight: 500;
  color: var(--text-color-secondary, #666); text-align: right;
  flex-shrink: 0;
}
.bar-track {
  flex: 1; height: 28px;
  background: var(--bar-bg, rgba(0, 0, 0, 0.06));
  border-radius: 6px; overflow: hidden;
  display: flex; align-items: center;
}
.bar-fill {
  height: 100%; min-height: 28px;
  display: flex; align-items: center; justify-content: flex-end;
  padding-right: 8px;
  transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.bar-value {
  font-size: 11px; font-weight: 600; color: #fff;
  white-space: nowrap;
}
</style>
