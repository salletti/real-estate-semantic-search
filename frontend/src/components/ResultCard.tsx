import type { PropertySearchResult, SearchResponse } from '../types'

interface Props {
  result: PropertySearchResult
  response: SearchResponse
}

function formatPrice(price: number | null): string {
  if (price === null) return ''
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(price)
}

function propertyTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    house: 'Maison',
    apartment: 'Appartement',
    villa: 'Villa',
    studio: 'Studio',
    loft: 'Loft',
    land: 'Terrain',
    commercial: 'Local commercial',
    parking: 'Parking',
  }
  return labels[type] ?? type
}

function scoreLabel(score: number): { text: string; color: string; bar: string } {
  if (score >= 0.80) return { text: 'Très pertinent', color: 'text-green-700', bar: 'bg-green-500' }
  if (score >= 0.60) return { text: 'Pertinent',      color: 'text-yellow-700', bar: 'bg-yellow-400' }
  return                     { text: 'Faiblement pertinent', color: 'text-orange-700', bar: 'bg-orange-400' }
}

const DESCRIPTION_MAX_CHARS = 180

export default function ResultCard({ result, response }: Props) {
  const strategy = response.query_resolution.strategy
  const isNearbySearch = !!response.nearby_city

  const truncatedDesc = result.description_fr
    ? result.description_fr.length > DESCRIPTION_MAX_CHARS
      ? result.description_fr.slice(0, DESCRIPTION_MAX_CHARS).trimEnd() + '…'
      : result.description_fr
    : null

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow">
      {/* Header: title + badges */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-semibold text-gray-900">
            {propertyTypeLabel(result.property_type)}
          </h3>
          <p className="text-sm text-gray-600 mt-0.5">
            {result.city}
            {result.rooms_count !== null && (
              <span className="text-gray-400">
                {' '}· {result.rooms_count} pièce{result.rooms_count > 1 ? 's' : ''}
              </span>
            )}
            {result.mandate_price !== null && (
              <span className="font-medium text-gray-900"> · {formatPrice(result.mandate_price)}</span>
            )}
          </p>
        </div>

        <div className="flex flex-wrap gap-1 justify-end shrink-0">
          {isNearbySearch && (
            <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">
              Proche
            </span>
          )}
          {strategy === 'hybrid' && (
            <span className="text-xs bg-purple-100 text-purple-800 px-2 py-0.5 rounded-full">
              Correspond bien
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      {truncatedDesc && (
        <p className="mt-2 text-sm text-gray-500 leading-relaxed">
          {truncatedDesc}
        </p>
      )}

      {/* Score de pertinence sémantique */}
      {result.score !== null && (() => {
        const { text, color, bar } = scoreLabel(result.score)
        const pct = Math.round(result.score * 100)
        return (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-400">Pertinence sémantique</span>
              <span className={`text-xs font-semibold ${color}`}>
                {pct}% — {text}
              </span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-1.5">
              <div
                className={`${bar} h-1.5 rounded-full transition-all`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )
      })()}
    </div>
  )
}
