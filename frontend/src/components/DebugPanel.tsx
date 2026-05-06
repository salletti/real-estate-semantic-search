import type { SearchResponse } from '../types'

interface Props {
  response: SearchResponse
}

interface SectionProps {
  label: string
  data: unknown
}

function Section({ label, data }: SectionProps) {
  return (
    <div>
      <p className="text-yellow-400 text-xs mb-1">// {label}</p>
      <pre className="text-green-300 text-xs overflow-x-auto whitespace-pre-wrap break-words">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}

export default function DebugPanel({ response }: Props) {
  const { parsed_intent: intent, query_resolution: resolution } = response

  return (
    <div className="bg-gray-900 text-gray-100 rounded-lg p-4">
      <h3 className="text-gray-400 text-sm font-semibold mb-4 font-sans">
        Debug — Moteur NLP
      </h3>

      <div className="space-y-5 font-mono">
        <Section
          label="Stratégie"
          data={{ strategy: resolution.strategy, reason: resolution.reason }}
        />

        <Section
          label="Intent structuré"
          data={{
            intent: intent.intent,
            llm_used: intent.llm_used,
            city: intent.city,
            property_type: intent.property_type,
            max_price: intent.max_price,
            min_rooms: intent.min_rooms,
            mandate_type: intent.mandate_type,
            transaction_type: intent.transaction_type,
            agent_name: intent.agent_name,
          }}
        />

        <Section
          label="Termes sémantiques"
          data={{ semantic_terms: intent.semantic_terms }}
        />

        {intent.nearby_city && (
          <Section
            label="Recherche de proximité"
            data={{
              nearby_city: response.nearby_city,
              search_radius_km: response.search_radius_km,
              expanded_cities: response.expanded_cities,
            }}
          />
        )}
      </div>
    </div>
  )
}
