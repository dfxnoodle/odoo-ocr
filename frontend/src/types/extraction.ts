export type WeightUnit = 'KG' | 'LBS' | 'MT'
export type ContainerSize = '20' | '40' | '45' | '40HC' | '45HC' | 'OTHER'
export type ContainerType = 'GP' | 'HC' | 'RF' | 'OT' | 'FR' | 'TK' | 'OTHER'

export interface WeightEntry {
  value: number | null
  unit: WeightUnit | null
}

export interface EIRExtraction {
  container_number: string | null
  seal_number: string | null
  container_size: ContainerSize | null
  container_type: ContainerType | null
  condition: string | null
  shipping_line: string | null
  vessel_name: string | null
  voyage_number: string | null
  bill_of_lading: string | null
  booking_number: string | null
  port_of_loading: string | null
  port_of_discharge: string | null
  place_of_receipt: string | null
  gross_weight: WeightEntry | null
  net_weight: WeightEntry | null
  tare_weight: WeightEntry | null
  receipt_date: string | null
  discharge_date: string | null
  shipper: string | null
  consignee: string | null
  notify_party: string | null
  commodity: string | null
  package_count: number | null
  package_type: string | null
  extraction_confidence: number | null
  language_hints: string[] | null
}

export interface ExtractionResponse {
  request_id: string
  filename: string
  extraction: EIRExtraction
  warnings: string[]
  provider_used: string
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
