import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { EIRExtraction, ExtractionResponse, OdooCommitResult } from '@/types/extraction'

export type UploadState = 'idle' | 'uploading' | 'extracting' | 'ready' | 'committing' | 'committed' | 'error'

export const useExtractionStore = defineStore('extraction', () => {
  const state = ref<UploadState>('idle')
  const error = ref<string | null>(null)

  // Uploaded file metadata
  const file = ref<File | null>(null)
  const fileUrl = ref<string | null>(null)

  // API response data
  const requestId = ref<string | null>(null)
  const extraction = ref<EIRExtraction | null>(null)
  const warnings = ref<string[]>([])
  const providerUsed = ref<string | null>(null)

  // Commit result
  const commitResult = ref<OdooCommitResult | null>(null)

  function setFile(f: File) {
    if (fileUrl.value) URL.revokeObjectURL(fileUrl.value)
    file.value = f
    fileUrl.value = URL.createObjectURL(f)
    state.value = 'idle'
    error.value = null
    extraction.value = null
    commitResult.value = null
    warnings.value = []
  }

  function setExtractionResponse(response: ExtractionResponse) {
    requestId.value = response.request_id
    extraction.value = { ...response.extraction }
    warnings.value = response.warnings
    providerUsed.value = response.provider_used
    state.value = 'ready'
    error.value = null
  }

  function updateField<K extends keyof EIRExtraction>(key: K, value: EIRExtraction[K]) {
    if (!extraction.value) return
    extraction.value[key] = value
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
    extraction.value = null
    warnings.value = []
    providerUsed.value = null
    commitResult.value = null
  }

  return {
    state,
    error,
    file,
    fileUrl,
    requestId,
    extraction,
    warnings,
    providerUsed,
    commitResult,
    setFile,
    setExtractionResponse,
    updateField,
    setCommitResult,
    setError,
    reset,
  }
})
