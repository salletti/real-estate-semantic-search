export interface PropertySearchResult {
  id: number
  city: string
  property_type: string
  transaction_type: string
  mandate_price: number | null
  rooms_count: number | null
  created_at: string
  score: number | null
  description_fr: string | null
}

export interface ParsedIntent {
  intent: string
  llm_used: boolean
  city: string | null
  nearby_city: string | null
  search_radius_km: number | null
  property_type: string | null
  max_price: number | null
  min_rooms: number | null
  mandate_type: string | null
  transaction_type: string | null
  published_more_than_days: number | null
  published_less_than_days: number | null
  agent_name: string | null
  semantic_terms: string[]
}

export interface QueryResolution {
  strategy: string
  reason: string
}

export interface SearchResponse {
  query: string
  parsed_intent: ParsedIntent
  query_resolution: QueryResolution
  count: number
  page: number
  per_page: number
  total_pages: number
  results: PropertySearchResult[]
  nearby_city: string | null
  search_radius_km: number | null
  expanded_cities: string[]
}
