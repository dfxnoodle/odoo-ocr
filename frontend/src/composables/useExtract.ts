import axios, { AxiosError } from 'axios'
import { useExtractionStore } from '@/stores/extraction'
import type { ExtractionResponse } from '@/types/extraction'

export function useExtract() {
  const store = useExtractionStore()

  async function extract(file: File, providerOverride?: string): Promise<void> {
    store.state = 'extracting'
    store.error = null

    const form = new FormData()
    form.append('file', file)
    if (providerOverride) {
      form.append('provider_override', providerOverride)
    }

    try {
      const { data } = await axios.post<ExtractionResponse>('/api/v1/extract', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      store.setExtractionResponse(data)
    } catch (err) {
      const msg = resolveErrorMessage(err)
      store.setError(msg)
      throw err
    }
  }

  return { extract }
}

function resolveErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => d.msg ?? d).join('; ')
    return err.message
  }
  return String(err)
}
