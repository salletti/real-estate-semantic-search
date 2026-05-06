interface Props {
  value: string
  onChange: (v: string) => void
  onSearch: (query: string) => void
  loading: boolean
}

export default function SearchBar({ value, onChange, onSearch, loading }: Props) {
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (value.trim()) onSearch(value.trim())
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder='Ex : "Maison proche de Rambouillet", "appartement lumineux Paris"…'
        className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
      />
      <button
        type="submit"
        disabled={loading || !value.trim()}
        className="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? 'Recherche…' : 'Rechercher'}
      </button>
    </form>
  )
}
