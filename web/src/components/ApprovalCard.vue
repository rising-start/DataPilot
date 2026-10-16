<template>
  <el-dialog
    v-model="visible"
    width="60%"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
  >
    <template #header>
      <div class="dialog-head">
        <el-icon class="card-icon"><Cpu /></el-icon>
        <span>{{ approval?.title || '执行审批' }}</span>
      </div>
    </template>
    <p class="tip">
      以下内容将在服务端执行（{{ language === 'sql' ? 'SQL' : 'Python 代码' }}），请确认后再批准。
    </p>
    <pre v-if="!editing" class="code"><code>{{ approval?.content }}</code></pre>
    <el-input
      v-else
      v-model="edited"
      type="textarea"
      :rows="12"
      class="editor"
      spellcheck="false"
    />
    <template #footer>
      <el-button type="danger" plain :loading="busy" @click="emit('decide', false)">
        拒绝执行
      </el-button>
      <el-button v-if="!editing" plain @click="startEdit">
        修改
      </el-button>
      <el-button v-else plain :disabled="busy" @click="cancelEdit">
        取消修改
      </el-button>
      <el-button
        type="primary"
        :loading="busy"
        @click="emit('decide', true, editing ? edited : null)"
      >
        批准执行
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Cpu } from '@element-plus/icons-vue'
import type { Approval } from '../types'

const props = defineProps<{ approval: Approval | null; busy: boolean }>()
const emit = defineEmits<{
  (e: 'decide', approved: boolean, modifiedContent?: string | null): void
}>()



const visible = ref(true)
watch(
  () => props.approval,
  () => {
    visible.value = true
    
    editing.value = false
    edited.value = props.approval?.content ?? ''
  },
)

const language = computed(() => props.approval?.language ?? 'python')


const editing = ref(false)
const edited = ref('')
function startEdit() {
  edited.value = props.approval?.content ?? ''
  editing.value = true
}
function cancelEdit() {
  editing.value = false
  edited.value = ''
}
</script>

<style scoped>
.dialog-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

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

.editor {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

.editor :deep(.el-textarea__inner) {
  background: #1f2430;
  color: #e6e6e6;
  font-size: 13px;
}
</style>
