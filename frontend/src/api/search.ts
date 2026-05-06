import type { SearchResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function searchProperties(
  query: string,
  page: number = 1,
  perPage: number = 10,
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query,
    page: String(page),
    per_page: String(perPage),
  })

  const res = await fetch(`${API_BASE_URL}/properties/search?${params}`)

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Erreur API ${res.status}: ${body}`)
  }

  return res.json() as Promise<SearchResponse>
}
