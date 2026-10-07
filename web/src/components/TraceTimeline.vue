<template>
  <el-card shadow="never">
    <template #header>执行链路（{{ trace.length }} 步）</template>
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
defineProps<{ trace: Record<string, any>[] }>()
</script>

<style scoped>
.detail {
  margin: 8px 0 0;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  max-height: 240px;
  overflow: auto;
}
</style>
