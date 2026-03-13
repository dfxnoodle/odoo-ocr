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
      </div>
      <div class="doc-preview">
        <img
          v-if="isImage"
          :src="store.fileUrl ?? ''"
          alt="Document preview"
          class="doc-preview__img"
        />
        <canvas v-else ref="pdfCanvas" class="doc-preview__canvas" />
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

        <!-- Row 1: Container + Gate info -->
        <fieldset class="form-group">
          <legend>Container</legend>
          <div class="field-grid">
            <label class="field">
              <span>Container No.</span>
              <input v-model="form.container_number" type="text" placeholder="e.g. MSCU1234567" />
            </label>
            <label class="field">
              <span>Size / Type — Size</span>
              <select v-model="form.container_size">
                <option value="">— Select —</option>
                <option v-for="o in containerSizeOptions" :key="o" :value="o">{{ o }}</option>
              </select>
            </label>
            <label class="field">
              <span>Size / Type — Type</span>
              <select v-model="form.container_type">
                <option value="">— Select —</option>
                <option v-for="o in containerTypeOptions" :key="o" :value="o">{{ o }}</option>
              </select>
            </label>
            <label class="field">
              <span>Seal No.</span>
              <input v-model="form.seal_number" type="text" />
            </label>
          </div>
        </fieldset>

        <!-- Row 2: EIR gate details -->
        <fieldset class="form-group">
          <legend>Gate / EIR</legend>
          <div class="field-grid">
            <label class="field">
              <span>EIR No.</span>
              <input v-model="form.eir_number" type="text" />
            </label>
            <label class="field">
              <span>In / Out</span>
              <select v-model="form.in_out_direction">
                <option value="">— Select —</option>
                <option value="IN">IN</option>
                <option value="OUT">OUT</option>
              </select>
            </label>
            <label class="field">
              <span>Designation</span>
              <input v-model="form.designation" type="text" />
            </label>
          </div>
        </fieldset>

        <!-- Row 3: Shipping -->
        <fieldset class="form-group">
          <legend>Shipping</legend>
          <div class="field-grid">
            <label class="field">
              <span>Shipping Line</span>
              <input v-model="form.shipping_line" type="text" />
            </label>
            <label class="field">
              <span>Vessel / Voyage — Vessel</span>
              <input v-model="form.vessel_name" type="text" />
            </label>
            <label class="field">
              <span>Vessel / Voyage — Voyage</span>
              <input v-model="form.voyage_number" type="text" />
            </label>
            <label class="field">
              <span>Release Order / Booking</span>
              <input v-model="form.booking_number" type="text" />
            </label>
          </div>
        </fieldset>

        <!-- Row 4: Weight -->
        <fieldset class="form-group">
          <legend>Weight</legend>
          <div class="field-grid">
            <label class="field">
              <span>Weight</span>
              <div class="weight-input">
                <input v-model.number="form.gross_weight_value" type="number" step="0.01" placeholder="0.00" />
                <select v-model="form.gross_weight_unit">
                  <option>KG</option><option>LBS</option><option>MT</option>
                </select>
              </div>
            </label>
          </div>
        </fieldset>

        <!-- Row 5: Dates -->
        <fieldset class="form-group">
          <legend>Dates</legend>
          <div class="field-grid">
            <label class="field">
              <span>Date of Issue</span>
              <input v-model="form.receipt_date" type="date" />
            </label>
            <label class="field">
              <span>Date of Discharge</span>
              <input v-model="form.discharge_date" type="date" />
            </label>
            <label class="field">
              <span>D.O Validity</span>
              <input v-model="form.do_validity_date" type="date" />
            </label>
          </div>
        </fieldset>

        <!-- Row 6: Documents -->
        <fieldset class="form-group">
          <legend>Documents</legend>
          <div class="field-grid">
            <label class="field">
              <span>D.O. No.</span>
              <input v-model="form.do_number" type="text" />
            </label>
            <label class="field">
              <span>Bill of Entry No.</span>
              <input v-model="form.bill_of_entry_number" type="text" />
            </label>
          </div>
        </fieldset>

        <!-- Row 7: Parties -->
        <fieldset class="form-group">
          <legend>Parties</legend>
          <div class="field-grid">
            <label class="field">
              <span>Consignee / Shipper</span>
              <input v-model="form.consignee" type="text" />
            </label>
            <label class="field">
              <span>Agent</span>
              <input v-model="form.agent" type="text" />
            </label>
            <label class="field">
              <span>Haulier</span>
              <input v-model="form.haulier" type="text" />
            </label>
            <label class="field">
              <span>Vehicle No.</span>
              <input v-model="form.vehicle_number" type="text" />
            </label>
          </div>
        </fieldset>

        <!-- Row 8: Misc -->
        <fieldset class="form-group">
          <legend>Additional</legend>
          <div class="field-grid">
            <label class="field field--full">
              <span>Remarks</span>
              <input v-model="form.remarks" type="text" />
            </label>
            <label class="field">
              <span>User Name</span>
              <input v-model="form.user_name" type="text" />
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
import type { ContainerSize, ContainerType, WeightUnit } from '@/types/extraction'

const store = useExtractionStore()
const router = useRouter()
const { commit } = useCommit()

function switchPage(index: number) {
  store.goToPage(index)
  populateForm()
}

const pdfCanvas = ref<HTMLCanvasElement | null>(null)
const pdfLoading = ref(false)
const dryRun = ref(false)

const isImage = computed(() => {
  const mime = store.file?.type ?? ''
  return mime.startsWith('image/')
})

const isCommitting = computed(() => store.state === 'committing')

const containerSizeOptions: ContainerSize[] = ['20', '40', '45', '40HC', '45HC', 'OTHER']
const containerTypeOptions: ContainerType[] = ['GP', 'HC', 'RF', 'OT', 'FR', 'TK', 'OTHER']

const confidenceBadgeClass = computed(() => {
  const c = store.extraction?.extraction_confidence ?? 0
  if (c >= 0.85) return 'badge--success'
  if (c >= 0.6) return 'badge--warning'
  return 'badge--danger'
})

// Flat reactive form — one field per EIR label
const form = reactive({
  // Container
  container_number: '',
  container_size: '' as ContainerSize | '',
  container_type: '' as ContainerType | '',
  seal_number: '',
  // Gate / EIR
  eir_number: '',
  in_out_direction: '',
  designation: '',
  // Shipping
  shipping_line: '',
  vessel_name: '',
  voyage_number: '',
  booking_number: '',
  // Weight
  gross_weight_value: null as number | null,
  gross_weight_unit: 'KG' as WeightUnit,
  // Dates
  receipt_date: '',
  discharge_date: '',
  do_validity_date: '',
  // Documents
  do_number: '',
  bill_of_entry_number: '',
  // Parties
  consignee: '',
  agent: '',
  haulier: '',
  vehicle_number: '',
  // Misc
  remarks: '',
  user_name: '',
})

function populateForm() {
  const e = store.extraction
  if (!e) return
  // Container
  form.container_number = e.container_number ?? ''
  form.container_size = (e.container_size as ContainerSize) ?? ''
  form.container_type = (e.container_type as ContainerType) ?? ''
  form.seal_number = e.seal_number ?? ''
  // Gate / EIR
  form.eir_number = e.eir_number ?? ''
  form.in_out_direction = e.in_out_direction ?? ''
  form.designation = e.designation ?? ''
  // Shipping
  form.shipping_line = e.shipping_line ?? ''
  form.vessel_name = e.vessel_name ?? ''
  form.voyage_number = e.voyage_number ?? ''
  form.booking_number = e.booking_number ?? ''
  // Weight
  form.gross_weight_value = e.gross_weight?.value ?? null
  form.gross_weight_unit = (e.gross_weight?.unit as WeightUnit) ?? 'KG'
  // Dates
  form.receipt_date = e.receipt_date ?? ''
  form.discharge_date = e.discharge_date ?? ''
  form.do_validity_date = e.do_validity_date ?? ''
  // Documents
  form.do_number = e.do_number ?? ''
  form.bill_of_entry_number = e.bill_of_entry_number ?? ''
  // Parties
  form.consignee = e.consignee ?? ''
  form.agent = e.agent ?? ''
  form.haulier = e.haulier ?? ''
  form.vehicle_number = e.vehicle_number ?? ''
  // Misc
  form.remarks = e.remarks ?? ''
  form.user_name = e.user_name ?? ''
}

function formToExtraction() {
  const e = store.extraction!
  return {
    ...e,
    // Container
    container_number: form.container_number || null,
    container_size: (form.container_size || null) as ContainerSize | null,
    container_type: (form.container_type || null) as ContainerType | null,
    seal_number: form.seal_number || null,
    // Gate / EIR
    eir_number: form.eir_number || null,
    in_out_direction: form.in_out_direction || null,
    designation: form.designation || null,
    // Shipping
    shipping_line: form.shipping_line || null,
    vessel_name: form.vessel_name || null,
    voyage_number: form.voyage_number || null,
    booking_number: form.booking_number || null,
    // Weight
    gross_weight: form.gross_weight_value != null
      ? { value: form.gross_weight_value, unit: form.gross_weight_unit }
      : null,
    // Dates
    receipt_date: form.receipt_date || null,
    discharge_date: form.discharge_date || null,
    do_validity_date: form.do_validity_date || null,
    // Documents
    do_number: form.do_number || null,
    bill_of_entry_number: form.bill_of_entry_number || null,
    // Parties
    consignee: form.consignee || null,
    agent: form.agent || null,
    haulier: form.haulier || null,
    vehicle_number: form.vehicle_number || null,
    // Misc
    remarks: form.remarks || null,
    user_name: form.user_name || null,
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
  align-items: flex-start;
  justify-content: center;
  padding: 12px;
  background: #f0f0f0;
}
.doc-preview__img,
.doc-preview__canvas {
  max-width: 100%;
  border-radius: 4px;
  box-shadow: var(--shadow-md);
}
.doc-preview__loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-subtle);
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
