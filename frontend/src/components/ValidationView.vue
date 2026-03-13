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
          {{ Math.round((store.extraction.extraction_confidence ?? 0) * 100) }}% confidence
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
      <div class="panel__header">
        <h2 class="panel__title">Extracted Fields</h2>
        <span class="panel__subtitle">Review and correct before committing to Odoo</span>
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
              <span>Container Number</span>
              <input v-model="form.container_number" type="text" placeholder="e.g. MSCU1234567" />
            </label>
            <label class="field">
              <span>Seal Number</span>
              <input v-model="form.seal_number" type="text" />
            </label>
            <label class="field">
              <span>Size</span>
              <select v-model="form.container_size">
                <option value="">— Select —</option>
                <option v-for="o in containerSizeOptions" :key="o" :value="o">{{ o }}</option>
              </select>
            </label>
            <label class="field">
              <span>Type</span>
              <select v-model="form.container_type">
                <option value="">— Select —</option>
                <option v-for="o in containerTypeOptions" :key="o" :value="o">{{ o }}</option>
              </select>
            </label>
            <label class="field">
              <span>Condition</span>
              <input v-model="form.condition" type="text" placeholder="e.g. CLEAN" />
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Shipping References</legend>
          <div class="field-grid">
            <label class="field">
              <span>Shipping Line</span>
              <input v-model="form.shipping_line" type="text" />
            </label>
            <label class="field">
              <span>Vessel Name</span>
              <input v-model="form.vessel_name" type="text" />
            </label>
            <label class="field">
              <span>Voyage Number</span>
              <input v-model="form.voyage_number" type="text" />
            </label>
            <label class="field">
              <span>Bill of Lading</span>
              <input v-model="form.bill_of_lading" type="text" />
            </label>
            <label class="field">
              <span>Booking Number</span>
              <input v-model="form.booking_number" type="text" />
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Ports & Routing</legend>
          <div class="field-grid">
            <label class="field">
              <span>Port of Loading</span>
              <input v-model="form.port_of_loading" type="text" />
            </label>
            <label class="field">
              <span>Port of Discharge</span>
              <input v-model="form.port_of_discharge" type="text" />
            </label>
            <label class="field">
              <span>Place of Receipt</span>
              <input v-model="form.place_of_receipt" type="text" />
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Weight</legend>
          <div class="field-grid field-grid--3">
            <label class="field">
              <span>Gross Weight</span>
              <div class="weight-input">
                <input
                  v-model.number="form.gross_weight_value"
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                />
                <select v-model="form.gross_weight_unit">
                  <option>KG</option><option>LBS</option><option>MT</option>
                </select>
              </div>
            </label>
            <label class="field">
              <span>Net Weight</span>
              <div class="weight-input">
                <input v-model.number="form.net_weight_value" type="number" step="0.01" placeholder="0.00" />
                <select v-model="form.net_weight_unit">
                  <option>KG</option><option>LBS</option><option>MT</option>
                </select>
              </div>
            </label>
            <label class="field">
              <span>Tare Weight</span>
              <div class="weight-input">
                <input v-model.number="form.tare_weight_value" type="number" step="0.01" placeholder="0.00" />
                <select v-model="form.tare_weight_unit">
                  <option>KG</option><option>LBS</option><option>MT</option>
                </select>
              </div>
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Dates</legend>
          <div class="field-grid">
            <label class="field">
              <span>Receipt Date</span>
              <input v-model="form.receipt_date" type="date" />
            </label>
            <label class="field">
              <span>Discharge Date</span>
              <input v-model="form.discharge_date" type="date" />
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Parties</legend>
          <div class="field-grid">
            <label class="field">
              <span>Shipper</span>
              <input v-model="form.shipper" type="text" />
            </label>
            <label class="field">
              <span>Consignee</span>
              <input v-model="form.consignee" type="text" />
            </label>
            <label class="field">
              <span>Notify Party</span>
              <input v-model="form.notify_party" type="text" />
            </label>
          </div>
        </fieldset>

        <fieldset class="form-group">
          <legend>Cargo</legend>
          <div class="field-grid">
            <label class="field">
              <span>Commodity</span>
              <input v-model="form.commodity" type="text" />
            </label>
            <label class="field">
              <span>Package Count</span>
              <input v-model.number="form.package_count" type="number" min="0" />
            </label>
            <label class="field">
              <span>Package Type</span>
              <input v-model="form.package_type" type="text" />
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

// Flat reactive form bound from store extraction
const form = reactive({
  container_number: '',
  seal_number: '',
  container_size: '' as ContainerSize | '',
  container_type: '' as ContainerType | '',
  condition: '',
  shipping_line: '',
  vessel_name: '',
  voyage_number: '',
  bill_of_lading: '',
  booking_number: '',
  port_of_loading: '',
  port_of_discharge: '',
  place_of_receipt: '',
  gross_weight_value: null as number | null,
  gross_weight_unit: 'KG' as WeightUnit,
  net_weight_value: null as number | null,
  net_weight_unit: 'KG' as WeightUnit,
  tare_weight_value: null as number | null,
  tare_weight_unit: 'KG' as WeightUnit,
  receipt_date: '',
  discharge_date: '',
  shipper: '',
  consignee: '',
  notify_party: '',
  commodity: '',
  package_count: null as number | null,
  package_type: '',
})

function populateForm() {
  const e = store.extraction
  if (!e) return
  form.container_number = e.container_number ?? ''
  form.seal_number = e.seal_number ?? ''
  form.container_size = (e.container_size as ContainerSize) ?? ''
  form.container_type = (e.container_type as ContainerType) ?? ''
  form.condition = e.condition ?? ''
  form.shipping_line = e.shipping_line ?? ''
  form.vessel_name = e.vessel_name ?? ''
  form.voyage_number = e.voyage_number ?? ''
  form.bill_of_lading = e.bill_of_lading ?? ''
  form.booking_number = e.booking_number ?? ''
  form.port_of_loading = e.port_of_loading ?? ''
  form.port_of_discharge = e.port_of_discharge ?? ''
  form.place_of_receipt = e.place_of_receipt ?? ''
  form.gross_weight_value = e.gross_weight?.value ?? null
  form.gross_weight_unit = (e.gross_weight?.unit as WeightUnit) ?? 'KG'
  form.net_weight_value = e.net_weight?.value ?? null
  form.net_weight_unit = (e.net_weight?.unit as WeightUnit) ?? 'KG'
  form.tare_weight_value = e.tare_weight?.value ?? null
  form.tare_weight_unit = (e.tare_weight?.unit as WeightUnit) ?? 'KG'
  form.receipt_date = e.receipt_date ?? ''
  form.discharge_date = e.discharge_date ?? ''
  form.shipper = e.shipper ?? ''
  form.consignee = e.consignee ?? ''
  form.notify_party = e.notify_party ?? ''
  form.commodity = e.commodity ?? ''
  form.package_count = e.package_count ?? null
  form.package_type = e.package_type ?? ''
}

function formToExtraction() {
  const e = store.extraction!
  return {
    ...e,
    container_number: form.container_number || null,
    seal_number: form.seal_number || null,
    container_size: (form.container_size || null) as ContainerSize | null,
    container_type: (form.container_type || null) as ContainerType | null,
    condition: form.condition || null,
    shipping_line: form.shipping_line || null,
    vessel_name: form.vessel_name || null,
    voyage_number: form.voyage_number || null,
    bill_of_lading: form.bill_of_lading || null,
    booking_number: form.booking_number || null,
    port_of_loading: form.port_of_loading || null,
    port_of_discharge: form.port_of_discharge || null,
    place_of_receipt: form.place_of_receipt || null,
    gross_weight: form.gross_weight_value != null
      ? { value: form.gross_weight_value, unit: form.gross_weight_unit }
      : null,
    net_weight: form.net_weight_value != null
      ? { value: form.net_weight_value, unit: form.net_weight_unit }
      : null,
    tare_weight: form.tare_weight_value != null
      ? { value: form.tare_weight_value, unit: form.tare_weight_unit }
      : null,
    receipt_date: form.receipt_date || null,
    discharge_date: form.discharge_date || null,
    shipper: form.shipper || null,
    consignee: form.consignee || null,
    notify_party: form.notify_party || null,
    commodity: form.commodity || null,
    package_count: form.package_count,
    package_type: form.package_type || null,
  }
}

// Load PDF preview
async function loadPdf() {
  if (!store.fileUrl || isImage.value || !pdfCanvas.value) return
  pdfLoading.value = true
  try {
    const { getDocument, GlobalWorkerOptions } = await import('pdfjs-dist')
    GlobalWorkerOptions.workerSrc = new URL(
      'pdfjs-dist/build/pdf.worker.min.mjs',
      import.meta.url,
    ).href
    const pdf = await getDocument(store.fileUrl).promise
    const page = await pdf.getPage(1)
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
  if (!store.extraction) {
    router.replace('/')
    return
  }
  populateForm()
  if (!isImage.value) loadPdf()
})

watch(() => store.extraction, populateForm, { deep: true })

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
</style>
