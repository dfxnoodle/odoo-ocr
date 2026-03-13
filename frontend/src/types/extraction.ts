export type WeightUnit = 'KG' | 'LBS' | 'MT'
export type ContainerSize = '20' | '40' | '45' | '40HC' | '45HC' | 'OTHER'
export type ContainerType = 'GP' | 'HC' | 'RF' | 'OT' | 'FR' | 'TK' | 'OTHER'

export interface WeightEntry {
  value: number | null
  unit: WeightUnit | null
}

export interface EIRExtraction {
  // Container
  container_number: string | null
  container_size: ContainerSize | null
  container_type: ContainerType | null
  seal_number: string | null
  // Gate / EIR
  eir_number: string | null
  in_out_direction: string | null
  designation: string | null
  // Shipping
  shipping_line: string | null
  vessel_name: string | null
  voyage_number: string | null
  booking_number: string | null
  // Weight
  gross_weight: WeightEntry | null
  // Dates
  receipt_date: string | null
  discharge_date: string | null
  do_validity_date: string | null
  // Documents
  do_number: string | null
  bill_of_entry_number: string | null
  // Parties
  consignee: string | null
  agent: string | null
  haulier: string | null
  vehicle_number: string | null
  // Misc
  remarks: string | null
  user_name: string | null
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
