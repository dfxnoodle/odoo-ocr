import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  EIRExtraction,
  ExtractionBatchResponse,
  ExtractionResponse,
  OdooCommitResult,
} from '@/types/extraction'

export type UploadState = 'idle' | 'uploading' | 'extracting' | 'ready' | 'committing' | 'committed' | 'error'

export interface PageProgressEntry {
  page: number
  total: number
  container_number: string | null
}

export const useExtractionStore = defineStore('extraction', () => {
  const state = ref<UploadState>('idle')
  const error = ref<string | null>(null)

  // Uploaded file metadata
  const file = ref<File | null>(null)
  const fileUrl = ref<string | null>(null)

  // Batch API response
  const requestId = ref<string | null>(null)
  const providerUsed = ref<string | null>(null)
  const allExtractions = ref<ExtractionResponse[]>([])
  const currentPageIndex = ref(0)   // 0-based index into allExtractions

  // Streaming progress (populated during extraction before the final result arrives)
  const progressPages = ref<PageProgressEntry[]>([])
  const progressTotal = ref(0)

  // Commit result
  const commitResult = ref<OdooCommitResult | null>(null)

  // ── Derived helpers ─────────────────────────────────────────────────────────
  const totalPages = computed(() => allExtractions.value.length)

  const currentResponse = computed<ExtractionResponse | null>(
    () => allExtractions.value[currentPageIndex.value] ?? null,
  )

  /** Current EIRExtraction (mutable via updateField) */
  const extraction = computed<EIRExtraction | null>(
    () => currentResponse.value?.extraction ?? null,
  )

  const warnings = computed<string[]>(
    () => currentResponse.value?.warnings ?? [],
  )

  // ── Actions ─────────────────────────────────────────────────────────────────
  function setFile(f: File) {
    if (fileUrl.value) URL.revokeObjectURL(fileUrl.value)
    file.value = f
    fileUrl.value = URL.createObjectURL(f)
    state.value = 'idle'
    error.value = null
    allExtractions.value = []
    currentPageIndex.value = 0
    progressPages.value = []
    progressTotal.value = 0
    commitResult.value = null
  }

  function addPageProgress(entry: PageProgressEntry) {
    progressTotal.value = entry.total
    progressPages.value.push(entry)
  }

  function setBatchResponse(response: ExtractionBatchResponse) {
    requestId.value = response.request_id
    providerUsed.value = response.provider_used
    // Deep-copy each extraction so form edits don't alias API data
    allExtractions.value = response.extractions.map((r) => ({
      ...r,
      extraction: { ...r.extraction },
    }))
    currentPageIndex.value = 0
    progressPages.value = []
    progressTotal.value = 0
    state.value = 'ready'
    error.value = null
  }

  function goToPage(index: number) {
    if (index >= 0 && index < allExtractions.value.length) {
      currentPageIndex.value = index
    }
  }

  function updateField<K extends keyof EIRExtraction>(key: K, value: EIRExtraction[K]) {
    const resp = allExtractions.value[currentPageIndex.value]
    if (resp) resp.extraction[key] = value
  }

  function setCommitResult(result: OdooCommitResult) {
    commitResult.value = result
    state.value = 'committed'
  }

  function setError(msg: string) {
    error.value = msg
    state.value = 'error'
  }

  function reset() {
    if (fileUrl.value) URL.revokeObjectURL(fileUrl.value)
    state.value = 'idle'
    error.value = null
    file.value = null
    fileUrl.value = null
    requestId.value = null
    allExtractions.value = []
    currentPageIndex.value = 0
    providerUsed.value = null
    progressPages.value = []
    progressTotal.value = 0
    commitResult.value = null
  }

  return {
    state,
    error,
    file,
    fileUrl,
    requestId,
    providerUsed,
    allExtractions,
    currentPageIndex,
    totalPages,
    currentResponse,
    extraction,
    warnings,
    commitResult,
    progressPages,
    progressTotal,
    setFile,
    setBatchResponse,
    addPageProgress,
    goToPage,
    updateField,
    setCommitResult,
    setError,
    reset,
  }
})
