<template>
  <el-card shadow="never">
    <template #header>数据源</template>
    <el-upload
      :show-file-list="false"
      :http-request="handleUpload"
      accept=".csv,.xlsx,.xls,.sqlite,.db"
    >
      <el-button type="primary">上传 CSV / Excel / SQLite</el-button>
    </el-upload>
    <p v-if="filename" class="file-name">当前文件：{{ filename }}（{{ sourceType }}）</p>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadFile } from '../api/tasks'

const emit = defineEmits<{ (e: 'uploaded', fileId: string): void }>()

const filename = ref('')
const sourceType = ref('')

async function handleUpload(options: any) {
  try {
    const result = await uploadFile(options.file)
    filename.value = result.filename
    sourceType.value = result.source_type
    emit('uploaded', result.file_id)
    options.onSuccess?.(result)
  } catch (e: any) {
    ElMessage.error(`上传失败：${e?.message ?? e}`)
    options.onError?.(e)
  }
}
</script>

<style scoped>
.file-name {
  margin: 8px 0 0;
  color: #606266;
  font-size: 13px;
}
</style>
