<template>
  <el-card shadow="never">
    <template #header>
      <el-icon class="card-icon"><EditPen /></el-icon>
      <span>分析问题</span>
    </template>
    <el-input
      v-model="question"
      type="textarea"
      :rows="3"
      resize="none"
      placeholder="例如：各渠道销售额排名，给我柱状图和结论。"
    />
    <div class="actions">
      <el-button type="primary" :loading="busy" :disabled="!canSubmit" @click="onStart">
        开始分析
      </el-button>
      <el-button :loading="busy" :disabled="!canFollowup" @click="onFollowup">
        基于上次结果继续追问
      </el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { EditPen } from '@element-plus/icons-vue'

const props = defineProps<{
  fileId: string | null
  hasPrevious: boolean
  busy: boolean
}>()

const emit = defineEmits<{ (e: 'submit', question: string, followup: boolean): void }>()

const question = ref('')

const canSubmit = computed(() => !!props.fileId && !!question.value.trim())
const canFollowup = computed(() => canSubmit.value && props.hasPrevious)

function submit(followup: boolean) {
  if (!canSubmit.value) {
    ElMessage.warning('请先上传文件并输入问题。')
    return
  }
  emit('submit', question.value.trim(), followup)
}

function onStart() {
  submit(false)
}

function onFollowup() {
  submit(true)
}
</script>

<style scoped>
.actions {
  margin-top: 14px;
  display: flex;
  gap: 12px;
}
</style>
