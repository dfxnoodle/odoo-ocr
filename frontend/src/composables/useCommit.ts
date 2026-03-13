import axios, { AxiosError } from 'axios'
import { useExtractionStore } from '@/stores/extraction'
import type { CommitRequest, OdooCommitResult } from '@/types/extraction'

export function useCommit() {
  const store = useExtractionStore()

  async function commit(odooModel = 'stock.picking', dryRun = false): Promise<OdooCommitResult> {
    if (!store.requestId || !store.extraction || !store.currentResponse) {
      throw new Error('No extraction data to commit.')
    }

    store.state = 'committing'
    store.error = null

    const payload: CommitRequest = {
      request_id: store.requestId,
      extraction: store.extraction,
      odoo_model: odooModel,
      dry_run: dryRun,
    }

    try {
      const { data } = await axios.post<OdooCommitResult>('/api/v1/odoo/commit', payload)
      store.setCommitResult(data)
      return data
    } catch (err) {
      const msg = resolveErrorMessage(err)
      store.setError(msg)
      throw err
    }
  }

  return { commit }
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
