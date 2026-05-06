import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchProperties } from '../api/search'
import SearchBar from '../components/SearchBar'
import ResultCard from '../components/ResultCard'
import DebugPanel from '../components/DebugPanel'
import Pagination from '../components/Pagination'

const PER_PAGE = 10
const README_SEARCH_EXAMPLES = [
  'Maison à Paris',
  'Appartement à Lyon',
  'Maison sous 500k',
  'Appartement 3 chambres à Marseille',
  'Maison avec jardin',
  'Biens à Paris avec mandat exclusif',
  'Appartements exclusifs à Lyon',
  'Biens publiés depuis plus de 30 jours',
  'Biens publiés il y a plus de 60 jours',
  'Biens publiés depuis moins de 7 jours',
  'Biens exclusifs publiés depuis 45 jours',
  'Les biens de Marie Dupont',
  'Voir les biens de Jean Martin',
  'Biens exclusifs de Sophie Bernard',
  'Biens de Marie Dupont publiés depuis plus de 30 jours',
  'Maison proche de Paris',
  'Appartement à côté de Lyon',
  'Biens autour de Marseille',
  'Biens aux alentours de Nantes',
  'Maison dans un rayon de 20km de Bordeaux',
  'Appartement T3 pres de Toulouse sous 300k',
  'Biens dans les environs de Le Havre',
  'Biens proche de VilleInconnue',
  'Biens familiaux à Paris sous 500k',
  'Maisons lumineuses avec jardin',
  'Appartements en baisse de prix depuis 30 jours',
  'Mandats exclusifs de Marie Dupont à Lyon',
  'Biens similaires à cet appartement',
  "Biens avec fort potentiel d'investissement",
] as const

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['search', query, page],
    queryFn: () => searchProperties(query, page, PER_PAGE),
    enabled: query.length > 0,
    staleTime: 30_000,
  })

  function handleSearch(q: string) {
    setQuery(q)
    setPage(1)
  }

  function handlePageChange(newPage: number) {
    setPage(newPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto px-4 py-8">

        {/* Header */}
        <header className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Real Estate AI Copilot</h1>
          <p className="text-sm text-gray-500 mt-1">
            Recherche en langage naturel · NLP → Intent → Résultats
          </p>
        </header>

        {/* Search bar */}
        <div className="mb-8">
          <SearchBar onSearch={handleSearch} loading={isLoading} />
        </div>

        <section className="mb-8 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-900">Exemples de recherches</h2>
          <p className="mt-1 text-xs text-gray-500">
            Extraits du README pour montrer les recherches possibles.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {README_SEARCH_EXAMPLES.map(example => (
              <button
                key={example}
                type="button"
                onClick={() => handleSearch(example)}
                className="rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 text-left text-xs text-gray-700 transition hover:border-gray-300 hover:bg-gray-100"
              >
                {example}
              </button>
            ))}
          </div>
        </section>

        {/* Loading */}
        {isLoading && (
          <div className="text-center text-gray-400 py-16 text-sm">
            Analyse de la requête et recherche en cours…
          </div>
        )}

        {/* Error */}
        {isError && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm">
            {error instanceof Error ? error.message : 'Erreur inconnue'}
          </div>
        )}

        {/* Results layout */}
        {data && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">

            {/* Left column: results list */}
            <div className="lg:col-span-2 space-y-3">
              {/* Summary sentence */}
              <p className="text-sm text-gray-600">
                <span className="font-semibold text-gray-900">{data.count}</span>{' '}
                bien{data.count > 1 ? 's' : ''} trouvé{data.count > 1 ? 's' : ''} correspondant à votre recherche.
              </p>

              {/* Result cards */}
              {data.results.length > 0 ? (
                data.results.map(result => (
                  <ResultCard key={result.id} result={result} response={data} />
                ))
              ) : (
                <p className="text-sm text-gray-400 py-8 text-center">
                  Aucun résultat pour cette recherche.
                </p>
              )}

              {/* Pagination */}
              <Pagination
                page={data.page}
                totalPages={data.total_pages}
                onPageChange={handlePageChange}
              />
            </div>

            {/* Right column: debug panel */}
            <div className="lg:col-span-1">
              <div className="sticky top-4">
                <DebugPanel response={data} />
              </div>
            </div>
          </div>
        )}

        {/* Empty state — before any search */}
        {!data && !isLoading && !isError && (
          <div className="text-center text-gray-400 py-20">
            <p className="text-4xl mb-4">🔍</p>
            <p className="text-sm">Tapez une requête pour commencer.</p>
            <div className="mt-4 space-y-1 text-xs text-gray-300">
              <p>"Maison proche de Rambouillet"</p>
              <p>"Appartement lumineux Paris sous 400k"</p>
              <p>"Studio calme vue mer"</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
