import { AlertTriangle } from 'lucide-react'

export default function DemoBanner({ dataMode = 'demo' }: { dataMode?: 'real' | 'demo' | 'unavailable' }) {
  if (dataMode === 'real') return null
  const unavailable = dataMode === 'unavailable'
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs ${unavailable ? 'bg-red-950/70 border-2 border-red-500 text-red-200' : 'bg-amber-950/40 border border-amber-800/40 text-amber-400'}`}>
      <AlertTriangle className="w-3 h-3 flex-shrink-0" />
      <span>
        <strong>{unavailable ? 'DATA UNAVAILABLE' : 'DEMO / SIMULATION DATA'}</strong> — {unavailable ? 'The expected real source could not be reached or validated.' : 'All displayed values are synthetically generated. Not for real navigation.'}
      </span>
    </div>
  )
}
