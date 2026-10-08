<template>
  <el-card shadow="never">
    <template #header>
      <el-icon class="card-icon"><Connection /></el-icon>
      <span>执行链路（{{ trace.length }} 步）</span>
    </template>
    <el-collapse>
      <el-collapse-item
        v-for="(item, index) in trace"
        :key="index"
        :title="`Step ${index + 1}: ${item.stage}`"
        :name="String(index)"
      >
        <el-tag :type="item.status === 'ok' ? 'success' : 'danger'" size="small">
          {{ item.status }}
        </el-tag>
        <pre class="detail">{{ JSON.stringify(item.detail, null, 2) }}</pre>
      </el-collapse-item>
    </el-collapse>
  </el-card>
</template>

<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'

defineProps<{ trace: Record<string, any>[] }>()
</script>

<style scoped>
.detail {
  margin: 8px 0 0;
  padding: 10px 12px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  max-height: 240px;
  overflow: auto;
}
</style>
