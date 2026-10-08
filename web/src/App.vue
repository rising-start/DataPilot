<template>
  <div class="app">
    <header class="app-header">
      <div class="brand">
        <div class="logo">DP</div>
        <div class="titles">
          <h1>DataPilot</h1>
          <span class="sub">用自然语言分析你的数据</span>
        </div>
      </div>
      <div class="header-meta">LangGraph 数据分析 Agent</div>
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
.app {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 28px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 15px;
  color: #fff;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
}

.titles {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.titles h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.titles .sub {
  color: var(--color-text-2);
  font-size: 12px;
}

.header-meta {
  color: var(--color-text-3);
  font-size: 12px;
  padding: 4px 12px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface-2);
}

.app-main {
  flex: 1;
  padding: 24px;
}
</style>
