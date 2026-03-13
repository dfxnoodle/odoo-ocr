import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  EIRExtraction,
  ExtractionBatchResponse,
  ExtractionResponse,
  OdooCommitResult,
  ProviderInfo,
} from '@/types/extraction'

export type UploadState = 'idle' | 'uploading' | 'extracting' | 'ready' | 'committing' | 'committed' | 'error'

export interface PageProgressEntry {
  page: number
  total: number
  container_number: string | null
}

export interface RetryingPageInfo {
  label: string
  attempt: number
  switchingProject: boolean
}

export const useExtractionStore = defineStore('extraction', () => {
  const state = ref<UploadState>('idle')
  const error = ref<string | null>(null)

  // Provider selection
  const providers = ref<ProviderInfo[]>([])
  const providersLoading = ref(false)
  const selectedProvider = ref<string | null>(null)

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

  // Set while a page is being retried after a rate-limit (429) error
  const retryingPage = ref<RetryingPageInfo | null>(null)

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

  async function loadProviders() {
    if (providersLoading.value) return
    providersLoading.value = true
    try {
      const res = await fetch('/api/v1/providers')
      if (!res.ok) return
      const data = await res.json()
      providers.value = data.providers ?? []
      // Auto-select first available provider if none chosen yet
      if (!selectedProvider.value) {
        const first = providers.value.find((p) => p.available)
        if (first) selectedProvider.value = first.id
      }
    } catch {
      // Non-fatal — selector stays hidden until providers load
    } finally {
      providersLoading.value = false
    }
  }

  function setProvider(id: string) {
    selectedProvider.value = id
  }

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
    retryingPage.value = null
  }

  function setRetryingPage(info: RetryingPageInfo) {
    retryingPage.value = info
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
    retryingPage.value = null
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
    retryingPage.value = null
    commitResult.value = null
  }

  return {
    state,
    error,
    providers,
    providersLoading,
    selectedProvider,
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
    retryingPage,
    loadProviders,
    setProvider,
    setFile,
    setBatchResponse,
    addPageProgress,
    setRetryingPage,
    goToPage,
    updateField,
    setCommitResult,
    setError,
    reset,
  }
})
