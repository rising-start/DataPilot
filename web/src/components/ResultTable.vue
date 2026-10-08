<template>
  <el-card v-if="rows.length" shadow="never">
    <template #header>
      <el-icon class="card-icon"><Grid /></el-icon>
      <span>数据明细（{{ rows.length }} 行）</span>
    </template>
    <el-table :data="rows" border stripe max-height="360" size="small">
      <el-table-column
        v-for="col in columns"
        :key="col"
        :prop="col"
        :label="col"
        show-overflow-tooltip
      />
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Grid } from '@element-plus/icons-vue'
import type { Row } from '../types'

const props = defineProps<{ rows: Row[] }>()

// 取所有行的列并集，避免行之间字段不一致时丢列
const columns = computed(() => {
  const keys = new Set<string>()
  props.rows.forEach((row) => Object.keys(row ?? {}).forEach((k) => keys.add(k)))
  return Array.from(keys)
})
</script>
