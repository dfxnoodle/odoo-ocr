export type WeightUnit = 'KG' | 'MT'
export type ContainerSize = '20' | '40' | '45' | '40HC' | '45HC' | 'OTHER'

export interface WeightEntry {
  value: number | null
  unit: WeightUnit | null
}

export interface EIRExtraction {
  // Container
  container_number: string | null
  seal_number: string | null
  container_size: ContainerSize | null
  // Transport
  vehicle_number: string | null
  haulier: string | null
  // Gate timestamp (ISO 8601 datetime string)
  receipt_date: string | null
  // Weight
  gross_weight: WeightEntry | null
  // Metadata
  extraction_confidence: number | null
  language_hints: string[] | null
}

export interface ExtractionResponse {
  request_id: string
  filename: string
  extraction: EIRExtraction
  warnings: string[]
  provider_used: string
  page_number: number
  total_pages: number
}

export interface ExtractionBatchResponse {
  request_id: string
  filename: string
  provider_used: string
  total_pages: number
  extractions: ExtractionResponse[]
}

export interface CommitRequest {
  request_id: string
  extraction: EIRExtraction
  odoo_model: string
  dry_run: boolean
}

export interface OdooCommitResult {
  success: boolean
  record_id: number | null
  odoo_model: string
  dry_run: boolean
  warnings: string[]
  unresolved_refs: Record<string, string>
}
