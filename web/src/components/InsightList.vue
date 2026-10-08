<template>
  <el-card shadow="never">
    <template #header>
      <el-icon class="card-icon"><Bulb /></el-icon>
      <span>关键发现</span>
    </template>
    <ul class="insights">
      <li v-for="(item, index) in insights" :key="index">
        <el-icon class="bullet"><MagicStick /></el-icon>
        <span>{{ item }}</span>
      </li>
    </ul>
    <el-divider />
    <h4>汇报结论</h4>
    <p class="report">{{ report || '—' }}</p>
  </el-card>
</template>

<script setup lang="ts">
import { MagicStick } from '@element-plus/icons-vue'

defineProps<{ insights: string[]; report: string }>()
</script>

<style scoped>
.insights {
  margin: 0;
  padding: 0;
  list-style: none;
  color: var(--color-text);
}

.insights li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
  line-height: 1.6;
}

.bullet {
  color: var(--color-primary);
  font-size: 14px;
  margin-top: 3px;
  flex: 0 0 auto;
}

.report {
  margin: 0;
  color: var(--color-text);
  line-height: 1.7;
  padding: 12px 14px;
  background: var(--color-surface-2);
  border-left: 3px solid var(--color-primary);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

h4 {
  margin: 0 0 10px;
  color: var(--color-text-2);
  font-size: 13px;
  font-weight: 600;
}
</style>
