<template>
  <div class="validation-layout">
    <!-- Left: Document preview -->
    <section class="panel panel--doc">
      <div class="panel__header">
        <h2 class="panel__title">Document Preview</h2>
        <span class="badge badge--provider">{{ store.providerUsed }}</span>
        <span
          v-if="store.extraction?.extraction_confidence != null"
          class="badge"
          :class="confidenceBadgeClass"
        >
          {{ Math.round((store.extraction?.extraction_confidence ?? 0) * 100) }}% confidence
        </span>
        <button class="rotate-btn" title="Rotate 90° clockwise" @click="rotateRight">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 2v6h-6"/>
            <path d="M21 8C19.6 5 16.9 3 13.5 3A9 9 0 0 0 4.5 12"/>
            <path d="M3 22v-6h6"/>
            <path d="M3 16c1.4 3 4.1 5 7.5 5A9 9 0 0 0 19.5 12"/>
          </svg>
        </button>
      </div>
      <div class="doc-preview">
        <img
          v-if="isImage"
          :src="store.fileUrl ?? ''"
          alt="Document preview"
          class="doc-preview__img"
          :style="{ transform: `rotate(${rotation}deg)` }"
        />
        <canvas
          v-else
          ref="pdfCanvas"
          class="doc-preview__canvas"
          :style="{ transform: `rotate(${rotation}deg)` }"
        />
        <div v-if="pdfLoading" class="doc-preview__loading">Loading PDF…</div>
      </div>
    </section>

    <!-- Right: Extraction form -->
    <section class="panel panel--form">
      <!-- Page tabs (only shown when PDF had multiple pages) -->
      <div v-if="store.totalPages > 1" class="page-tabs">
        <button
          v-for="(resp, idx) in store.allExtractions"
          :key="idx"
          class="page-tab"
          :class="{ 'page-tab--active': store.currentPageIndex === idx }"
          @click="switchPage(idx)"
        >
          <span class="page-tab__num">{{ idx + 1 }}</span>
          <span class="page-tab__cntr">{{ resp.extraction.container_number ?? '—' }}</span>
        </button>
      </div>

      <div class="panel__header">
        <h2 class="panel__title">Extracted Fields</h2>
        <span v-if="store.totalPages > 1" class="panel__subtitle">
          Page {{ store.currentPageIndex + 1 }} of {{ store.totalPages }}
        </span>
        <span v-else class="panel__subtitle">Review and correct before committing to Odoo</span>
      </div>

      <div v-if="store.warnings.length" class="alert alert-warning form-warnings">
        <div>
          <strong>Extraction warnings:</strong>
          <ul>
            <li v-for="w in store.warnings" :key="w">{{ w }}</li>
          </ul>
        </div>
      </div>

      <form class="extraction-form" @submit.prevent="onConfirm">

        <fieldset class="form-group">
          <legend>Container</legend>
          <div class="field-grid">
            <label class="field">
              <span>Container IN</span>
              <input v-model="form.container_number" type="text" placeholder="e.g. MSCU1234567" />
            </label>
            <label class="field">
              <span>Seal IN</span>
              <input v-model="form.seal_number" type="text" />
            </label>
            <label class="field">
              <span>ISO Size</span>
              <select v-model="form.container_size">
                <option value="">— Select —</option>
                <option v-for="o in containerSizeOptions" :key="o" :value="o">{{ o }}</option>
              </select>
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Transport</legend>
          <div class="field-grid">
            <label class="field">
              <span>Truck Plate IN</span>
              <input v-model="form.vehicle_number" type="text" />
            </label>
            <label class="field">
              <span>Supplier (Haulier)</span>
              <input v-model="form.haulier" type="text" />
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Gate</legend>
          <div class="field-grid">
            <label class="field">
              <span>IN Time</span>
              <input v-model="form.receipt_date" type="datetime-local" />
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Weight</legend>
          <div class="field-grid">
            <label class="field">
              <span>Declared Weight</span>
              <div class="weight-input">
                <input v-model.number="form.gross_weight_value" type="number" step="0.001" placeholder="0.00" />
                <select v-model="form.gross_weight_unit">
                  <option>KG</option><option>MT</option>
                </select>
              </div>
            </label>
          </div>
        </fieldset>

        <div class="form-footer">
          <button type="button" class="btn btn-secondary" @click="onCancel">← Back</button>
          <label class="dry-run-toggle">
            <input v-model="dryRun" type="checkbox" />
            Dry run (validate without saving)
          </label>
          <button type="submit" class="btn btn-success" :disabled="isCommitting">
            <span v-if="isCommitting" class="spinner spinner--dark" />
            {{ isCommitting ? 'Saving…' : 'Confirm & Push to Odoo' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useExtractionStore } from '@/stores/extraction'
import { useCommit } from '@/composables/useCommit'
import type { ContainerSize, WeightUnit } from '@/types/extraction'

const store = useExtractionStore()
const router = useRouter()
const { commit } = useCommit()

function switchPage(index: number) {
  store.goToPage(index)
  populateForm()
  rotation.value = 0
}

const pdfCanvas = ref<HTMLCanvasElement | null>(null)
const pdfLoading = ref(false)
const dryRun = ref(false)
const rotation = ref(0)   // degrees: 0 | 90 | 180 | 270

function rotateRight() {
  rotation.value = (rotation.value + 90) % 360
}

const isImage = computed(() => {
  const mime = store.file?.type ?? ''
  return mime.startsWith('image/')
})

const isCommitting = computed(() => store.state === 'committing')

const containerSizeOptions: ContainerSize[] = ['20', '40', '45', '40HC', '45HC', 'OTHER']

const confidenceBadgeClass = computed(() => {
  const c = store.extraction?.extraction_confidence ?? 0
  if (c >= 0.85) return 'badge--success'
  if (c >= 0.6) return 'badge--warning'
  return 'badge--danger'
})

// Flat reactive form — one field per Gate-IN required field
const form = reactive({
  container_number: '',
  seal_number: '',
  container_size: '' as ContainerSize | '',
  vehicle_number: '',
  haulier: '',
  receipt_date: '',          // datetime-local string: "YYYY-MM-DDTHH:MM"
  gross_weight_value: null as number | null,
  gross_weight_unit: 'KG' as WeightUnit,
})

function populateForm() {
  const e = store.extraction
  if (!e) return
  form.container_number = e.container_number ?? ''
  form.seal_number = e.seal_number ?? ''
  form.container_size = (e.container_size as ContainerSize) ?? ''
  form.vehicle_number = e.vehicle_number ?? ''
  form.haulier = e.haulier ?? ''
  // Convert ISO datetime "2026-03-12T03:21:00" → "2026-03-12T03:21" for datetime-local input
  form.receipt_date = e.receipt_date ? e.receipt_date.slice(0, 16) : ''
  form.gross_weight_value = e.gross_weight?.value ?? null
  form.gross_weight_unit = (e.gross_weight?.unit as WeightUnit) ?? 'KG'
}

function formToExtraction() {
  const e = store.extraction!
  return {
    ...e,
    container_number: form.container_number || null,
    seal_number: form.seal_number || null,
    container_size: (form.container_size || null) as ContainerSize | null,
    vehicle_number: form.vehicle_number || null,
    haulier: form.haulier || null,
    receipt_date: form.receipt_date ? `${form.receipt_date}:00` : null,  // append seconds for ISO 8601
    gross_weight: form.gross_weight_value != null
      ? { value: form.gross_weight_value, unit: form.gross_weight_unit }
      : null,
  }
}

// Load PDF preview
// Cached pdfjs document so we don't re-fetch the PDF on every tab switch
let pdfDocCache: import('pdfjs-dist').PDFDocumentProxy | null = null

async function renderPdfPage(pageNum: number) {
  if (!store.fileUrl || isImage.value || !pdfCanvas.value) return
  pdfLoading.value = true
  try {
    if (!pdfDocCache) {
      const { getDocument, GlobalWorkerOptions } = await import('pdfjs-dist')
      GlobalWorkerOptions.workerSrc = new URL(
        'pdfjs-dist/build/pdf.worker.min.mjs',
        import.meta.url,
      ).href
      pdfDocCache = await getDocument(store.fileUrl).promise
    }
    const page = await pdfDocCache.getPage(pageNum)
    const viewport = page.getViewport({ scale: 1.5 })
    const canvas = pdfCanvas.value!
    canvas.width = viewport.width
    canvas.height = viewport.height
    await page.render({ canvas, canvasContext: canvas.getContext('2d')!, viewport }).promise
  } catch (err) {
    console.error('PDF render error', err)
  } finally {
    pdfLoading.value = false
  }
}

onMounted(() => {
  if (!store.extraction || store.allExtractions.length === 0) {
    router.replace('/')
    return
  }
  populateForm()
  if (!isImage.value) renderPdfPage(store.currentPageIndex + 1)
})

watch(() => store.extraction, populateForm, { deep: true })

// Re-render the preview whenever the active tab changes
watch(
  () => store.currentPageIndex,
  (idx) => {
    if (!isImage.value) renderPdfPage(idx + 1)
  },
)

async function onConfirm() {
  if (!store.extraction) return
  store.updateField('container_number', form.container_number || null)
  // Apply all form values back to the store before commit
  const updated = formToExtraction()
  Object.assign(store.extraction, updated)

  try {
    await commit('stock.picking', dryRun.value)
    router.push('/committed')
  } catch {
    // error captured in store
  }
}

function onCancel() {
  router.push('/')
}
</script>

<style scoped>
.validation-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  height: calc(100vh - 52px - 64px);
  min-height: 600px;
}

@media (max-width: 900px) {
  .validation-layout {
    grid-template-columns: 1fr;
    height: auto;
  }
}

.panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel__header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.panel__title {
  font-size: 15px;
  font-weight: 600;
  margin-right: auto;
}

.panel__subtitle {
  font-size: 12px;
  color: var(--color-text-subtle);
}

.badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 20px;
  background: var(--color-surface-secondary);
  border: 1px solid var(--color-border);
}
.badge--provider { color: var(--color-primary); border-color: var(--color-primary); }
.badge--success { background: #f6ffed; color: #389e0d; border-color: #b7eb8f; }
.badge--warning { background: #fff7e6; color: #d46b08; border-color: #ffd591; }
.badge--danger { background: #fff1f0; color: #cf1322; border-color: #ffa39e; }

/* Document preview */
.doc-preview {
  flex: 1;
  overflow: auto;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #f0f0f0;
}
.doc-preview__img,
.doc-preview__canvas {
  max-width: 100%;
  border-radius: 4px;
  box-shadow: var(--shadow-md);
  transition: transform 0.25s ease;
  transform-origin: center center;
}
.doc-preview__loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-subtle);
}

/* Rotate button */
.rotate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text-subtle);
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.rotate-btn:hover {
  background: var(--color-surface-secondary, #f0f0f0);
  color: var(--color-primary);
  border-color: var(--color-primary);
}

/* Form */
.panel--form {
  overflow-y: auto;
}

.form-warnings {
  margin: 12px 18px 0;
}
.form-warnings ul {
  margin: 4px 0 0 16px;
}

.extraction-form {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 12px 16px;
}
.form-group legend {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-text-subtle);
  padding: 0 4px;
}

.field-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 8px;
}
.field-grid--3 {
  grid-template-columns: 1fr 1fr 1fr;
}
.field--full {
  grid-column: 1 / -1;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-subtle);
  font-weight: 500;
}
.field input,
.field select {
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: 13px;
  color: var(--color-text);
  background: var(--color-surface);
  transition: border-color 0.15s;
}
.field input:focus,
.field select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(0, 82, 204, 0.15);
}

.weight-input {
  display: flex;
  gap: 4px;
}
.weight-input input {
  flex: 1;
}
.weight-input select {
  width: 60px;
}

.form-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 4px;
  flex-wrap: wrap;
}
.dry-run-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-text-subtle);
  cursor: pointer;
  margin-right: auto;
}
.spinner--dark {
  border-color: rgba(0, 0, 0, 0.2);
  border-top-color: white;
}
.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Page navigation tabs */
.page-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 10px 0;
  background: var(--color-surface-secondary, #f5f5f5);
  border-bottom: 1px solid var(--color-border);
  overflow-x: auto;
  flex-shrink: 0;
}
.page-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 5px 10px 6px;
  border: 1px solid var(--color-border);
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  background: var(--color-surface);
  cursor: pointer;
  font-size: 11px;
  color: var(--color-text-subtle);
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.page-tab:hover {
  background: var(--color-surface-secondary, #f0f0f0);
  color: var(--color-text);
}
.page-tab--active {
  background: var(--color-surface);
  color: var(--color-primary);
  border-color: var(--color-primary);
  font-weight: 600;
  position: relative;
}
.page-tab--active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--color-surface);
}
.page-tab__num {
  font-size: 10px;
  opacity: 0.6;
}
.page-tab__cntr {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
}
</style>
