import { useQuery } from '@tanstack/react-query'
import { fetchSystemStatus } from '../services/api'
import type { FreshnessInfo } from '../types'

const DOT: Record<string, string> = {
  LIVE: 'bg-emerald-400',
  NEAR_REAL_TIME: 'bg-emerald-400',
  LATEST_AVAILABLE: 'bg-yellow-400',
  STALE: 'bg-orange-400',
  OFFLINE: 'bg-red-500',
  DEMO: 'bg-amber-400',
  UNKNOWN: 'bg-slate-500',
}

const LABEL: Record<string, string> = {
  LIVE: 'text-emerald-400',
  NEAR_REAL_TIME: 'text-emerald-400',
  LATEST_AVAILABLE: 'text-yellow-400',
  STALE: 'text-orange-400',
  OFFLINE: 'text-red-400',
  DEMO: 'text-amber-400',
  UNKNOWN: 'text-slate-500',
}

function SourceChip({ info }: { info: FreshnessInfo }) {
  const unavailable = info.data_mode === 'unavailable'
  const dot = unavailable ? 'bg-red-200 animate-pulse' : DOT[info.status] || DOT.UNKNOWN
  const lbl = unavailable ? 'text-red-100' : LABEL[info.status] || LABEL.UNKNOWN
  return (
    <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-polar-card border border-polar-border">
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`} />
      <span className="text-slate-400 text-xs">{info.source_name.replace('Sentinel-1 SAR', 'Satellite').replace('PostgreSQL / PostGIS', 'DB')}</span>
      <span className={`text-xs font-mono ${lbl}`}>
        {unavailable ? 'UNAVAILABLE' : info.status === 'DEMO' ? 'DEMO' : info.age_human || info.status_label}
      </span>
    </div>
  )
}

export default function SystemStatusBar() {
  const { data } = useQuery({
    queryKey: ['system-status'],
    queryFn: fetchSystemStatus,
    refetchInterval: 30_000,
  })

  if (!data?.sources?.length) return null

  const sources: FreshnessInfo[] = data.sources.filter((s: FreshnessInfo) =>
    ['ais', 'sea_ice', 'icebergs', 'weather', 'ocean', 'satellite', 'database'].includes(s.source_id)
  )

  const allDemo = sources.every(s => s.data_mode === 'demo' || s.status === 'DEMO')
  const anyUnavailable = sources.some(s => s.data_mode === 'unavailable' || s.status === 'OFFLINE')

  return (
    <div className="fixed bottom-0 left-60 right-0 z-50 border-t border-polar-border bg-polar-bg/95 backdrop-blur-sm px-4 py-1.5 flex items-center gap-2 overflow-x-auto">
      <span className="text-xs text-slate-600 flex-shrink-0 uppercase tracking-wider">Data</span>
      {sources.map(s => <SourceChip key={s.source_id} info={s} />)}
      {allDemo && (
        <span className="ml-auto text-xs text-amber-600 flex-shrink-0">
          ⚠ All sources in DEMO mode
        </span>
      )}
      {anyUnavailable && <span className="ml-auto text-xs text-red-300 font-semibold flex-shrink-0">⚠ REAL DATA UNAVAILABLE</span>}
      <span className="ml-auto text-xs text-slate-700 flex-shrink-0">
        Research prototype — not for navigation
      </span>
    </div>
  )
}
