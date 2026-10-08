<template>
  <el-card shadow="never">
    <template #header>
      <el-icon class="card-icon"><UploadFilled /></el-icon>
      <span>数据源</span>
    </template>
    <el-upload
      :show-file-list="false"
      :http-request="handleUpload"
      accept=".csv,.xlsx,.xls,.sqlite,.db"
      drag
      class="uploader"
    >
      <div class="upload-inner">
        <el-icon class="upload-cloud"><UploadFilled /></el-icon>
        <div class="upload-text">拖拽文件到此处，或<em>点击上传</em></div>
        <div class="upload-hint">支持 CSV / Excel / SQLite</div>
      </div>
    </el-upload>
    <div v-if="filename" class="file-chip">
      <el-icon><Document /></el-icon>
      <span class="file-name">{{ filename }}</span>
      <el-tag size="small" effect="plain" type="info">{{ sourceType }}</el-tag>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Document } from '@element-plus/icons-vue'
import { uploadFile } from '../api/tasks'

const emit = defineEmits<{ (e: 'uploaded', payload: { id: string; name: string }): void }>()

const filename = ref('')
const sourceType = ref('')

async function handleUpload(options: any) {
  try {
    const result = await uploadFile(options.file)
    filename.value = result.filename
    sourceType.value = result.source_type
    emit('uploaded', { id: result.file_id, name: result.filename })
    options.onSuccess?.(result)
  } catch (e: any) {
    ElMessage.error(`上传失败：${e?.message ?? e}`)
    options.onError?.(e)
  }
}
</script>

<style scoped>
.uploader :deep(.el-upload-dragger) {
  padding: 20px 12px;
  border-radius: var(--radius-sm);
  border-color: var(--color-border);
  background: var(--color-surface-2);
}

.upload-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.upload-cloud {
  font-size: 28px;
  color: var(--color-primary);
}

.upload-text {
  font-size: 13px;
  color: var(--color-text-2);
}

.upload-text em {
  color: var(--color-primary);
  font-style: normal;
  font-weight: 600;
}

.upload-hint {
  font-size: 11px;
  color: var(--color-text-3);
}

.file-chip {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-soft);
  border: 1px solid #d9d6fb;
}

.file-chip .file-name {
  flex: 1;
  font-size: 13px;
  color: var(--color-primary-active);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
