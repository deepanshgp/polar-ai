import type { FreshnessInfo } from '../types'

interface Props { freshness?: FreshnessInfo | null; compact?: boolean }

const COLOR: Record<string, string> = {
  unavailable: 'text-red-100 bg-red-950 border-red-500',
  LIVE: 'text-emerald-400 bg-emerald-950/40 border-emerald-700/30',
  NEAR_REAL_TIME: 'text-emerald-400 bg-emerald-950/30 border-emerald-800/20',
  LATEST_AVAILABLE: 'text-yellow-400 bg-yellow-950/40 border-yellow-700/30',
  STALE: 'text-orange-400 bg-orange-950/40 border-orange-700/30',
  OFFLINE: 'text-red-400 bg-red-950/40 border-red-700/30',
  DEMO: 'text-amber-400 bg-amber-950/40 border-amber-700/30',
  UNKNOWN: 'text-slate-500 bg-polar-bg border-polar-border',
}

export default function FreshnessTag({ freshness, compact = false }: Props) {
  if (!freshness) return null
  const mode = freshness.data_mode
  const cls = COLOR[mode || freshness.status] || COLOR.UNKNOWN
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-xs font-mono ${cls}`}>
      <span className="w-1 h-1 rounded-full bg-current" />
      {mode === 'unavailable' ? 'UNAVAILABLE' : compact ? freshness.age_human || freshness.status_label : `${freshness.status_label} · ${freshness.age_human}`}
    </span>
  )
}
