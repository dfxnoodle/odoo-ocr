import { useExtractionStore } from '@/stores/extraction'
import type { ExtractionBatchResponse } from '@/types/extraction'

export function useExtract() {
  const store = useExtractionStore()

  async function extract(file: File, providerOverride?: string): Promise<void> {
    store.state = 'extracting'
    store.error = null
    store.progressPages = []
    store.progressTotal = 0

    const form = new FormData()
    form.append('file', file)
    if (providerOverride) form.append('provider_override', providerOverride)

    let response: Response
    try {
      response = await fetch('/api/v1/extract', { method: 'POST', body: form })
    } catch (err) {
      store.setError(`Network error: ${String(err)}`)
      throw err
    }

    if (!response.ok) {
      // Non-2xx before streaming starts — read error body
      const body = await response.json().catch(() => ({}))
      const msg = body?.detail ?? `Server error ${response.status}`
      store.setError(msg)
      throw new Error(msg)
    }

    // ── Parse SSE stream ──────────────────────────────────────────────────
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE events are delimited by double newlines
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() ?? ''   // keep the incomplete tail

        for (const chunk of chunks) {
          const dataLine = chunk.split('\n').find((l) => l.startsWith('data: '))
          if (!dataLine) continue

          let event: Record<string, unknown>
          try {
            event = JSON.parse(dataLine.slice(6))
          } catch {
            continue
          }

          if (event.type === 'page_done') {
            store.addPageProgress({
              page: event.page as number,
              total: event.total as number,
              container_number: (event.container_number as string | null) ?? null,
            })
          } else if (event.type === 'result') {
            store.setBatchResponse(event.data as ExtractionBatchResponse)
          } else if (event.type === 'error') {
            const msg = (event.detail as string) ?? 'Extraction failed'
            store.setError(msg)
            throw new Error(msg)
          }
        }
      }
    } finally {
      reader.releaseLock()
    }

    if (store.state !== 'ready') {
      // Stream ended without a result event
      store.setError('Extraction stream ended unexpectedly.')
      throw new Error('Extraction stream ended unexpectedly.')
    }
  }

  return { extract }
}
