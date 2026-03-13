<template>
  <div
    class="uploader"
    :class="{ 'uploader--drag-over': isDragOver, 'uploader--has-file': hasFile }"
    @dragover.prevent="isDragOver = true"
    @dragleave="isDragOver = false"
    @drop.prevent="onDrop"
  >
    <input
      ref="inputRef"
      type="file"
      accept=".pdf,.jpg,.jpeg,.png,.webp,.tiff"
      class="uploader__input"
      @change="onFileChange"
    />

    <template v-if="!hasFile">
      <div class="uploader__icon">📄</div>
      <p class="uploader__title">Drop your EIR document here</p>
      <p class="uploader__hint">PDF, JPG, PNG, WEBP, TIFF — max {{ maxMb }} MB</p>
      <button class="btn btn-secondary uploader__browse" @click="inputRef?.click()">
        Browse files
      </button>
    </template>

    <template v-else>
      <div class="uploader__preview">
        <span class="uploader__filename">{{ store.file?.name }}</span>
        <span class="uploader__size">{{ fileSizeLabel }}</span>
      </div>
      <div class="uploader__actions">
        <button class="btn btn-primary" :disabled="isExtracting" @click="onExtract">
          <span v-if="isExtracting" class="spinner" />
          {{ isExtracting ? 'Extracting…' : 'Extract Data' }}
        </button>
        <button class="btn btn-secondary" :disabled="isExtracting" @click="onClear">
          Change file
        </button>
      </div>
    </template>

    <div v-if="localError" class="alert alert-error uploader__error">
      ⚠ {{ localError }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useExtractionStore } from '@/stores/extraction'
import { useExtract } from '@/composables/useExtract'

const props = withDefaults(defineProps<{ maxMb?: number }>(), { maxMb: 20 })

const store = useExtractionStore()
const router = useRouter()
const { extract } = useExtract()
const inputRef = ref<HTMLInputElement | null>(null)
const isDragOver = ref(false)
const localError = ref<string | null>(null)

const hasFile = computed(() => !!store.file)
const isExtracting = computed(() => store.state === 'extracting')
const fileSizeLabel = computed(() => {
  const bytes = store.file?.size ?? 0
  return bytes > 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.round(bytes / 1024)} KB`
})

const ALLOWED = new Set(['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/tiff'])

function validateAndSet(file: File) {
  localError.value = null
  if (!ALLOWED.has(file.type)) {
    localError.value = `Unsupported file type: ${file.type}. Please upload a PDF or image.`
    return
  }
  if (file.size > props.maxMb * 1024 * 1024) {
    localError.value = `File is too large (max ${props.maxMb} MB).`
    return
  }
  store.setFile(file)
}

function onFileChange(event: Event) {
  const f = (event.target as HTMLInputElement).files?.[0]
  if (f) validateAndSet(f)
}

function onDrop(event: DragEvent) {
  isDragOver.value = false
  const f = event.dataTransfer?.files?.[0]
  if (f) validateAndSet(f)
}

async function onExtract() {
  if (!store.file) return
  localError.value = null
  try {
    await extract(store.file)
    router.push('/validate')
  } catch {
    // error is already in store
  }
}

function onClear() {
  store.reset()
  localError.value = null
  if (inputRef.value) inputRef.value.value = ''
}
</script>

<style scoped>
.uploader {
  border: 2px dashed var(--color-border);
  border-radius: var(--radius);
  padding: 48px 32px;
  text-align: center;
  transition: border-color 0.2s, background 0.2s;
  cursor: default;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.uploader--drag-over {
  border-color: var(--color-primary);
  background: #e6f0ff;
}
.uploader--has-file {
  border-style: solid;
  border-color: var(--color-primary);
  background: #f8faff;
}
.uploader__input {
  display: none;
}
.uploader__icon {
  font-size: 40px;
  line-height: 1;
}
.uploader__title {
  font-size: 16px;
  font-weight: 600;
}
.uploader__hint {
  color: var(--color-text-subtle);
  font-size: 13px;
}
.uploader__browse {
  margin-top: 4px;
}
.uploader__preview {
  display: flex;
  align-items: center;
  gap: 10px;
}
.uploader__filename {
  font-weight: 600;
  font-size: 15px;
}
.uploader__size {
  color: var(--color-text-subtle);
  font-size: 12px;
}
.uploader__actions {
  display: flex;
  gap: 8px;
}
.uploader__error {
  width: 100%;
  max-width: 420px;
}
.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.5);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
