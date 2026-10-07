<template>
  <div class="app">
    <header class="app-header">
      <h1>DataPilot</h1>
      <span class="sub">LangGraph 数据分析 Agent</span>
    </header>
    <main class="app-main">
      <AnalysisPage />
    </main>
  </div>
</template>

<script setup lang="ts">
import AnalysisPage from './views/AnalysisPage.vue'
</script>

<style>
body {
  margin: 0;
  font-family: 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif;
  background: #f5f7fa;
}

.app-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.app-header h1 {
  margin: 0;
  font-size: 20px;
}

.app-header .sub {
  color: #909399;
  font-size: 13px;
}

.app-main {
  padding: 24px;
}
</style>
