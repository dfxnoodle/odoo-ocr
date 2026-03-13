<template>
  <div class="uploader-wrap">
    <!-- ── Provider selector ──────────────────────────────────────────────── -->
    <div class="provider-bar">
      <span class="provider-bar__label">OCR Provider</span>

      <div v-if="store.providersLoading" class="provider-bar__skeleton">
        <span v-for="n in 3" :key="n" class="provider-skeleton-pill" />
      </div>

      <div v-else class="provider-bar__options">
        <button
          v-for="p in store.providers"
          :key="p.id"
          class="provider-pill"
          :class="{
            'provider-pill--active': store.selectedProvider === p.id,
            'provider-pill--disabled': !p.available,
          }"
          :disabled="!p.available"
          :title="p.available ? p.description : (p.unavailable_reason ?? p.description)"
          @click="p.available && store.setProvider(p.id)"
        >
          <span class="provider-pill__icon">{{ providerIcon(p.id) }}</span>
          <span class="provider-pill__name">{{ p.label }}</span>
        </button>
      </div>
    </div>

    <!-- ── Drop zone / file preview / progress ───────────────────────────── -->
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

      <template v-else-if="!isExtracting">
        <div class="uploader__preview">
          <span class="uploader__filename">{{ store.file?.name }}</span>
          <span class="uploader__size">{{ fileSizeLabel }}</span>
        </div>
        <div class="uploader__actions">
          <button
            class="btn btn-primary"
            :disabled="!store.selectedProvider"
            :title="!store.selectedProvider ? 'No provider available' : undefined"
            @click="onExtract"
          >
            Extract Data
          </button>
          <button class="btn btn-secondary" @click="onClear">Change file</button>
        </div>
      </template>

      <!-- Extraction progress -->
      <template v-else>
        <div class="progress-block">
          <p class="progress-block__label">
            <span class="progress-block__status">Extracting document…</span>
            <span v-if="store.progressTotal > 0" class="progress-block__count">
              {{ store.progressPages.length }} / {{ store.progressTotal }}
            </span>
          </p>

          <div class="progress-bar" role="progressbar"
               :aria-valuenow="progressPercent"
               aria-valuemin="0" aria-valuemax="100">
            <div class="progress-bar__fill" :style="{ width: progressPercent + '%' }" />
          </div>

          <ul v-if="store.progressTotal > 0" class="progress-list">
            <li v-for="p in store.progressPages" :key="p.page" class="progress-list__item progress-list__item--done">
              <span class="progress-list__icon">✓</span>
              <span class="progress-list__page">Page {{ p.page }}</span>
              <span class="progress-list__cntr">{{ p.container_number ?? 'unknown container' }}</span>
            </li>
            <li
              v-for="(n, idx) in remainingPages"
              :key="'r' + n"
              class="progress-list__item"
              :class="idx === 0 && store.retryingPage
                ? 'progress-list__item--retrying'
                : 'progress-list__item--pending'"
            >
              <span
                class="progress-list__icon"
                :class="idx === 0 && store.retryingPage ? 'progress-list__icon--pulse' : 'progress-list__icon--spin'"
              >{{ idx === 0 && store.retryingPage ? '⚠' : '⟳' }}</span>
              <span class="progress-list__page">Page {{ store.progressPages.length + n }}</span>
              <span v-if="idx === 0 && store.retryingPage" class="progress-list__cntr progress-list__cntr--retry">
                <template v-if="store.retryingPage.switchingProject">
                  Rate limit — switching API project…
                </template>
                <template v-else>
                  Rate limit — waiting to retry (attempt {{ store.retryingPage.attempt }})…
                </template>
              </span>
              <span v-else class="progress-list__cntr">processing…</span>
            </li>
          </ul>
          <p v-else class="progress-block__init">Preparing pages…</p>
        </div>
      </template>

      <div v-if="localError" class="alert alert-error uploader__error">
        ⚠ {{ localError }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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

const progressPercent = computed(() => {
  if (store.progressTotal === 0) return 5
  return Math.round((store.progressPages.length / store.progressTotal) * 100)
})

const remainingPages = computed(() => {
  const remaining = store.progressTotal - store.progressPages.length
  return remaining > 0 ? Array.from({ length: remaining }, (_, i) => i + 1) : []
})

const fileSizeLabel = computed(() => {
  const bytes = store.file?.size ?? 0
  return bytes > 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.round(bytes / 1024)} KB`
})

const ALLOWED = new Set(['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/tiff'])

const PROVIDER_ICONS: Record<string, string> = {
  vertex: '☁',
  azure: '☁',
  paddle_vl: '⚡',
  paddle: '💻',
}

function providerIcon(id: string): string {
  return PROVIDER_ICONS[id] ?? '◆'
}

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

onMounted(() => {
  store.loadProviders()
})
</script>

<style scoped>
.uploader-wrap {
  display: flex;
  flex-direction: column;
}

/* ── Provider bar ────────────────────────────────────────────────────── */
.provider-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-secondary);
  flex-wrap: wrap;
}

.provider-bar__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-subtle);
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.provider-bar__options {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.provider-bar__skeleton {
  display: flex;
  gap: 6px;
}

.provider-skeleton-pill {
  width: 96px;
  height: 32px;
  border-radius: 20px;
  background: linear-gradient(90deg, #e8eaed 25%, #f5f6f7 50%, #e8eaed 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.provider-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 20px;
  border: 1.5px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, color 0.15s, opacity 0.15s;
  white-space: nowrap;
}

.provider-pill:hover:not(:disabled):not(.provider-pill--active) {
  border-color: var(--color-primary);
  background: #e6f0ff;
}

.provider-pill--active {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: white;
}

.provider-pill--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.provider-pill__icon {
  font-size: 12px;
  line-height: 1;
}

.provider-pill__name {
  line-height: 1;
}

/* ── Drop zone ───────────────────────────────────────────────────────── */
.uploader {
  border: 2px dashed var(--color-border);
  border-top: none;
  border-radius: 0 0 var(--radius) var(--radius);
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

/* ── Extraction progress ─────────────────────────────────────────────── */
.progress-block {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.progress-block__label {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 13px;
}

.progress-block__status {
  font-weight: 600;
  color: var(--color-text);
}

.progress-block__count {
  color: var(--color-text-subtle);
  font-variant-numeric: tabular-nums;
}

.progress-block__init {
  font-size: 12px;
  color: var(--color-text-subtle);
  text-align: center;
  margin: 0;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--color-border);
  border-radius: 99px;
  overflow: hidden;
}

.progress-bar__fill {
  height: 100%;
  background: var(--color-primary, #0052cc);
  border-radius: 99px;
  transition: width 0.4s ease;
}

.progress-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.progress-list__item {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
}

.progress-list__item--done {
  background: #f6ffed;
  border-color: #b7eb8f;
  color: #237804;
}

.progress-list__item--pending {
  background: var(--color-surface-secondary, #fafafa);
  color: var(--color-text-subtle);
}

.progress-list__item--retrying {
  background: #fffbe6;
  border-color: #ffe58f;
  color: #874d00;
}

.progress-list__icon {
  font-size: 13px;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

.progress-list__icon--spin {
  display: inline-block;
  animation: spin 1.2s linear infinite;
}

.progress-list__icon--pulse {
  display: inline-block;
  animation: pulse 1.6s ease-in-out infinite;
}

.progress-list__cntr--retry {
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 500;
}

.progress-list__page {
  font-weight: 600;
  flex-shrink: 0;
}

.progress-list__cntr {
  flex: 1;
  font-family: monospace;
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
</style>
