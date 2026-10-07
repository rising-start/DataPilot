<template>
  <el-dialog
    v-model="visible"
    :title="approval?.title || '执行审批'"
    width="60%"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
  >
    <p class="tip">
      以下内容将在服务端执行（{{ language === 'sql' ? 'SQL' : 'Python 代码' }}），请确认后再批准。
    </p>
    <pre class="code"><code>{{ approval?.content }}</code></pre>
    <template #footer>
      <el-button type="danger" plain :loading="busy" @click="emit('decide', false)">
        拒绝执行
      </el-button>
      <el-button type="primary" :loading="busy" @click="emit('decide', true)">
        批准执行
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Approval } from '../types'

const props = defineProps<{ approval: Approval | null; busy: boolean }>()
const emit = defineEmits<{ (e: 'decide', approved: boolean): void }>()

// 审批是唯一的恢复入口：不允许通过遮罩 / ESC / 右上角关闭，
// 否则任务会永久停在 awaiting_approval 且没有任何恢复按钮
const visible = ref(true)
watch(
  () => props.approval,
  () => {
    visible.value = true
  },
)

const language = computed(() => props.approval?.language ?? 'python')
</script>

<style scoped>
.tip {
  margin: 0 0 12px;
  color: #606266;
  font-size: 13px;
}

.code {
  margin: 0;
  padding: 12px;
  background: #1f2430;
  color: #e6e6e6;
  border-radius: 6px;
  max-height: 320px;
  overflow: auto;
  font-size: 13px;
}
</style>
