<template>
  <el-card shadow="never">
    <template #header>关键发现</template>
    <ul class="insights">
      <li v-for="(item, index) in insights" :key="index">{{ item }}</li>
    </ul>
    <el-divider />
    <h4>汇报结论</h4>
    <p class="report">{{ report || '—' }}</p>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{ insights: string[]; report: string }>()
</script>

<style scoped>
.insights {
  margin: 0;
  padding-left: 20px;
  color: #303133;
}

.insights li {
  margin-bottom: 6px;
}

.report {
  margin: 0;
  color: #303133;
  line-height: 1.7;
}

h4 {
  margin: 0 0 8px;
}
</style>
