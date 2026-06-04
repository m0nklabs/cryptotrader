/**
 * CoinDossier — daily LLM-generated analysis "dossier" per coin/pair.
 *
 * Shows a file-cabinet style view of all tracked coins with:
 * - Lore / background
 * - Stats summary
 * - Technical analysis narrative
 * - Retrospective on previous predictions
 * - New prediction / outlook
 * - Prediction tracking (correct / wrong)
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

// -----------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------

interface DossierEntry {
  id: number
  exchange: string
  symbol: string
  entry_date: string
  // Stats
  price: number
  change_24h: number
  change_7d: number
  volume_24h: number
  rsi: number
  macd_signal: string
  ema_trend: string
  support_level: number
  resistance_level: number
  signal_score: number
  // Narrative (may be omitted in compact list mode)
  lore?: string
  stats_summary?: string
  tech_analysis?: string
  retrospective?: string
  prediction?: string
  full_narrative?: string
  // Prediction tracking
  predicted_direction: string
  predicted_target: number
  predicted_timeframe: string
  prediction_correct: boolean | null
  // LLM Assessment (structured recommendation)
  assessment_action?: string  // BUY/SELL/HOLD/AVOID
  assessment_confidence?: number  // 1-10
  assessment_risk?: string  // low/medium/high/extreme
  assessment_entry_low?: number
  assessment_entry_high?: number
  assessment_stop_loss?: number
  assessment_take_profit_1?: number
  assessment_take_profit_2?: number
  assessment_reasoning?: string
  // Meta
  model_used: string
  tokens_used: number
  generation_time_ms: number
  created_at: string | null
}

type SortMode = 'alpha' | 'hot' | 'volume' | 'rsi' | 'score'

const SORT_OPTIONS: { value: SortMode; label: string; icon: string }[] = [
  { value: 'alpha', label: 'A–Z', icon: '🔤' },
  { value: 'hot', label: 'Hot (24h)', icon: '🔥' },
  { value: 'volume', label: 'Volume', icon: '📊' },
  { value: 'rsi', label: 'RSI', icon: '📈' },
  { value: 'score', label: 'Signal', icon: '⚡' },
]

function sortEntries(entries: DossierEntry[], mode: SortMode): DossierEntry[] {
  const sorted = [...entries]
  switch (mode) {
    case 'hot':
      return sorted.sort((a, b) => Math.abs(b.change_24h) - Math.abs(a.change_24h))
    case 'volume':
      return sorted.sort((a, b) => b.volume_24h - a.volume_24h)
    case 'rsi':
      // Sort by distance from 50 (most extreme = most interesting)
      return sorted.sort((a, b) => Math.abs(b.rsi - 50) - Math.abs(a.rsi - 50))
    case 'score':
      return sorted.sort((a, b) => Math.abs(b.signal_score) - Math.abs(a.signal_score))
    case 'alpha':
    default:
      return sorted.sort((a, b) => a.symbol.localeCompare(b.symbol))
  }
}

interface QueueStatus {
  state: 'idle' | 'running' | 'completed' | 'failed'
  total: number
  completed: number
  failed: number
  current_symbol: string | null
  progress_pct: number
  delay_seconds: number
}

// -----------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------

function DirectionBadge({ direction }: { direction: string }) {
  const colors: Record<string, string> = {
    up: 'bg-green-500/20 text-green-400 border-green-500/30',
    down: 'bg-red-500/20 text-red-400 border-red-500/30',
    sideways: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  }
  const icons: Record<string, string> = {
    up: '↗',
    down: '↘',
    sideways: '→',
  }
  const cls = colors[direction] || colors.sideways
  const icon = icons[direction] || icons.sideways

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-bold uppercase ${cls}`}>
      {icon} {direction}
    </span>
  )
}

function PredictionResult({ correct }: { correct: boolean | null }) {
  if (correct === null) return <span className="text-xs text-gray-500">pending</span>
  return correct ? (
    <span className="text-xs font-semibold text-green-400">✅ Correct</span>
  ) : (
    <span className="text-xs font-semibold text-red-400">❌ Wrong</span>
  )
}

function AssessmentBadge({ action }: { action?: string }) {
  if (!action) return null

  const colors: Record<string, string> = {
    BUY: 'bg-green-600/90 text-white border-green-500/50',
    SELL: 'bg-red-600/90 text-white border-red-500/50',
    HOLD: 'bg-amber-600/90 text-white border-amber-500/50',
    AVOID: 'bg-gray-600/90 text-white border-gray-500/50',
  }
  const icons: Record<string, string> = {
    BUY: '🟢',
    SELL: '🔴',
    HOLD: '🟡',
    AVOID: '⚫',
  }

  const normalizedAction = action.toUpperCase()
  const cls = colors[normalizedAction] || colors.HOLD
  const icon = icons[normalizedAction] || '◯'

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-bold uppercase ${cls}`}>
      {icon} {normalizedAction}
    </span>
  )
}

function AssessmentPanel({ entry }: { entry: DossierEntry }) {
  if (!entry.assessment_action) return null

  const action = entry.assessment_action.toUpperCase()
  const confidence = entry.assessment_confidence || 0
  const risk = entry.assessment_risk || ''

  // Background color based on action
  const bgColors: Record<string, string> = {
    BUY: 'bg-green-500/10 border-green-500/30',
    SELL: 'bg-red-500/10 border-red-500/30',
    HOLD: 'bg-amber-500/10 border-amber-500/30',
    AVOID: 'bg-gray-500/10 border-gray-500/30',
  }
  const bgClass = bgColors[action] || bgColors.HOLD

  // Risk color
  const riskColors: Record<string, string> = {
    low: 'text-green-400',
    medium: 'text-yellow-400',
    high: 'text-orange-400',
    extreme: 'text-red-400',
  }
  const riskColor = riskColors[risk.toLowerCase()] || 'text-gray-400'

  return (
    <div className={`rounded-lg border ${bgClass} p-4`}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🤖</span>
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">LLM Assessment</h3>
      </div>

      <div className="space-y-3">
        {/* Action and Metrics */}
        <div className="flex items-center gap-4">
          <AssessmentBadge action={action} />
          <div className="flex items-center gap-3 text-xs">
            <span className="text-gray-400">
              Confidence: <span className="font-semibold text-gray-200">{confidence}/10</span>
            </span>
            {risk && (
              <>
                <span className="text-gray-600">•</span>
                <span className="text-gray-400">
                  Risk: <span className={`font-semibold capitalize ${riskColor}`}>{risk}</span>
                </span>
              </>
            )}
          </div>
        </div>

        {/* Entry/Exit Levels */}
        {(entry.assessment_entry_low || entry.assessment_entry_high || entry.assessment_stop_loss) && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {entry.assessment_entry_low && entry.assessment_entry_high && (
              <div className="rounded bg-gray-800/50 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Entry Zone</div>
                <div className="text-sm font-semibold text-gray-200">
                  ${entry.assessment_entry_low.toLocaleString()} – ${entry.assessment_entry_high.toLocaleString()}
                </div>
              </div>
            )}
            {(entry.assessment_stop_loss ?? 0) > 0 && (
              <div className="rounded bg-gray-800/50 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Stop Loss</div>
                <div className="text-sm font-semibold text-red-400">
                  ${entry.assessment_stop_loss?.toLocaleString()}
                </div>
              </div>
            )}
            {(entry.assessment_take_profit_1 ?? 0) > 0 && (
              <div className="rounded bg-gray-800/50 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Target 1</div>
                <div className="text-sm font-semibold text-green-400">
                  ${entry.assessment_take_profit_1?.toLocaleString()}
                </div>
              </div>
            )}
            {(entry.assessment_take_profit_2 ?? 0) > 0 && (
              <div className="rounded bg-gray-800/50 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Target 2</div>
                <div className="text-sm font-semibold text-green-400">
                  ${entry.assessment_take_profit_2?.toLocaleString()}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Reasoning */}
        {entry.assessment_reasoning && (
          <div className="rounded bg-gray-800/30 px-3 py-2.5 text-sm leading-relaxed text-gray-400 italic">
            "{entry.assessment_reasoning}"
          </div>
        )}
      </div>
    </div>
  )
}

function StatPill({ label, value, suffix }: { label: string; value: string | number; suffix?: string }) {
  return (
    <div className="rounded-lg bg-gray-800/50 px-3 py-2 text-center">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-sm font-semibold text-gray-200">
        {value}{suffix}
      </div>
    </div>
  )
}

function NarrativeSection({
  title,
  icon,
  content,
  defaultOpen = true,
}: {
  title: string
  icon: string
  content?: string
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  if (!content) return null

  return (
    <div className="rounded-lg border border-gray-700/50 bg-gray-800/30">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium text-gray-300 hover:bg-gray-700/30"
      >
        <span>{icon}</span>
        <span className="flex-1">{title}</span>
        <span className="text-gray-500">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="border-t border-gray-700/30 px-4 py-3 text-sm leading-relaxed text-gray-400 whitespace-pre-line">
          {content}
        </div>
      )}
    </div>
  )
}

function CoinCard({
  entry,
  isSelected,
  onClick,
}: {
  entry: DossierEntry
  isSelected: boolean
  onClick: () => void
}) {
  const changeColor = entry.change_24h >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <button
      onClick={onClick}
      className={`w-full rounded-lg border p-3 text-left transition-all ${
        isSelected
          ? 'border-blue-500/50 bg-blue-500/10'
          : 'border-gray-700/50 bg-gray-800/30 hover:border-gray-600/50 hover:bg-gray-800/50'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-bold text-gray-200">{entry.symbol}</span>
          <DirectionBadge direction={entry.predicted_direction} />
          {entry.assessment_action && <AssessmentBadge action={entry.assessment_action} />}
        </div>
        <PredictionResult correct={entry.prediction_correct} />
      </div>
      <div className="mt-1 flex items-center gap-3 text-xs">
        <span className="text-gray-400">${entry.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        <span className={changeColor}>{entry.change_24h >= 0 ? '+' : ''}{entry.change_24h.toFixed(2)}%</span>
        <span className="text-gray-500">RSI {entry.rsi.toFixed(0)}</span>
      </div>
      <div className="mt-1 text-[11px] text-gray-500 line-clamp-2">
        {entry.stats_summary || entry.prediction || 'No analysis yet'}
      </div>
    </button>
  )
}

function QueueProgress({ status }: { status: QueueStatus }) {
  if (status.state === 'idle') return null
  const pct = status.progress_pct

  return (
    <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-blue-300">
          {status.state === 'running' ? (
            <span className="flex items-center gap-2">
              <span className="h-3 w-3 animate-spin rounded-full border border-blue-400/30 border-t-blue-400" />
              Generating {status.current_symbol}...
            </span>
          ) : status.state === 'completed' ? (
            `✅ Done — ${status.completed} dossiers generated`
          ) : (
            `❌ Queue failed`
          )}
        </span>
        <span className="text-blue-400 font-mono">{status.completed}/{status.total}</span>
      </div>
      <div className="mt-1 h-1.5 w-full rounded-full bg-gray-700/50">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function EmptyState({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-5xl mb-4">📁</div>
      <h3 className="text-lg font-semibold text-gray-300 mb-2">No Dossiers Yet</h3>
      <p className="text-sm text-gray-500 mb-6 max-w-md">
        Dossiers are generated automatically every day at 08:00 UTC.
        You can also queue a batch now — it will run in the background with
        pauses between each coin to keep hardware load low.
      </p>
      <button
        onClick={onGenerate}
        disabled={generating}
        className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {generating ? (
          <span className="flex items-center gap-2">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            Queued...
          </span>
        ) : (
          '🤖 Queue All Dossiers'
        )}
      </button>
    </div>
  )
}

// -----------------------------------------------------------------------
// Main component
// -----------------------------------------------------------------------

interface CoinDossierProps {
  exchange: string
}

export default function CoinDossier({ exchange }: CoinDossierProps) {
  const [entries, setEntries] = useState<DossierEntry[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [history, setHistory] = useState<DossierEntry[]>([])
  const [historyIndex, setHistoryIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [generatingSymbol, setGeneratingSymbol] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null)
  const [sortMode, setSortMode] = useState<SortMode>('alpha')

  const sortedEntries = useMemo(() => sortEntries(entries, sortMode), [entries, sortMode])

  // Fetch latest dossiers for all coins
  const fetchLatest = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetch(`/dossier/latest?exchange=${encodeURIComponent(exchange)}&compact=true`)
      if (!res.ok) {
        if (res.status === 404) {
          setEntries([])
          return
        }
        throw new Error(`Failed to fetch: ${res.status}`)
      }
      const data = await res.json()
      setEntries(data.entries || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dossiers')
    } finally {
      setLoading(false)
    }
  }, [exchange])

  // Fetch history for selected coin
  const fetchHistory = useCallback(async (symbol: string) => {
    try {
      const res = await fetch(`/dossier/${encodeURIComponent(symbol)}?exchange=${encodeURIComponent(exchange)}&days=30`)
      if (!res.ok) {
        setHistory([])
        return
      }
      const data = await res.json()
      setHistory(data.entries || [])
      setHistoryIndex(0)
    } catch {
      setHistory([])
    }
  }, [exchange])

  // Generate all dossiers (via queue — fire-and-forget)
  const handleGenerateAll = async () => {
    setGenerating(true)
    setError(null)
    try {
      const res = await fetch(`/dossier/generate-all?exchange=${encodeURIComponent(exchange)}&delay=10`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error(`Queue failed: ${res.status}`)
      // Start polling queue status
      pollQueueStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Queue failed')
      setGenerating(false)
    }
  }

  // Poll queue status while generating
  const pollQueueStatus = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/dossier/queue/status')
        if (!res.ok) return
        const status: QueueStatus = await res.json()
        setQueueStatus(status)

        // Refresh the dossier list as new ones come in
        if (status.completed > 0) {
          fetchLatest()
        }

        // Stop polling when done
        if (status.state !== 'running') {
          clearInterval(interval)
          setGenerating(false)
          // Final refresh
          await fetchLatest()
        }
      } catch {
        // ignore polling errors
      }
    }, 3000) // Poll every 3 seconds

    return () => clearInterval(interval)
  }, [fetchLatest])

  // Generate single dossier
  const handleGenerateSingle = async (symbol: string) => {
    setGeneratingSymbol(symbol)
    try {
      const res = await fetch(`/dossier/${encodeURIComponent(symbol)}/generate?exchange=${encodeURIComponent(exchange)}`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error(`Generation failed: ${res.status}`)
      await fetchLatest()
      if (selectedSymbol === symbol) {
        await fetchHistory(symbol)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
    } finally {
      setGeneratingSymbol(null)
    }
  }

  // Initial load
  useEffect(() => {
    fetchLatest()
    // Check if a queue is already running
    fetch('/dossier/queue/status')
      .then(r => r.ok ? r.json() : null)
      .then((status: QueueStatus | null) => {
        if (status && status.state === 'running') {
          setQueueStatus(status)
          setGenerating(true)
          pollQueueStatus()
        }
      })
      .catch(() => { /* ignore */ })
  }, [fetchLatest, pollQueueStatus])

  // Load history when symbol selected
  useEffect(() => {
    if (selectedSymbol) {
      fetchHistory(selectedSymbol)
    }
  }, [selectedSymbol, fetchHistory])

  const selectedEntry = history[historyIndex] || entries.find((e) => e.symbol === selectedSymbol)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-500" />
      </div>
    )
  }

  if (entries.length === 0) {
    return <EmptyState onGenerate={handleGenerateAll} generating={generating} />
  }

  return (
    <div className="flex gap-4 h-full min-h-0">
      {/* Left sidebar — coin list */}
      <div className="w-72 flex-shrink-0 space-y-2 overflow-y-auto rounded-lg border border-gray-700/50 bg-gray-900/50 p-3">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
            Dossiers ({entries.length})
          </h3>
          <button
            onClick={handleGenerateAll}
            disabled={generating}
            className="rounded bg-blue-600/80 px-2 py-1 text-[10px] font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            title="Queue dossier generation for all coins (staggered)"
          >
            {generating ? '⏳' : '🔄'}
          </button>
        </div>

        {/* Sort buttons */}
        <div className="flex flex-wrap gap-1 mb-2">
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setSortMode(opt.value)}
              className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                sortMode === opt.value
                  ? 'bg-blue-600/80 text-white'
                  : 'bg-gray-800/60 text-gray-400 hover:bg-gray-700/60 hover:text-gray-300'
              }`}
              title={`Sort by ${opt.label}`}
            >
              {opt.icon} {opt.label}
            </button>
          ))}
        </div>

        {/* Queue progress bar */}
        {queueStatus && queueStatus.state !== 'idle' && (
          <QueueProgress status={queueStatus} />
        )}

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">
            {error}
          </div>
        )}

        {sortedEntries.map((entry) => (
          <CoinCard
            key={entry.symbol}
            entry={entry}
            isSelected={selectedSymbol === entry.symbol}
            onClick={() => setSelectedSymbol(entry.symbol)}
          />
        ))}
      </div>

      {/* Right content — selected coin dossier */}
      <div className="flex-1 overflow-y-auto rounded-lg border border-gray-700/50 bg-gray-900/50 p-6">
        {!selectedEntry ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="text-4xl mb-3">📋</div>
            <p className="text-sm text-gray-500">Select a coin to view its dossier</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-gray-100">{selectedEntry.symbol}</h2>
                  <DirectionBadge direction={selectedEntry.predicted_direction} />
                  <PredictionResult correct={selectedEntry.prediction_correct} />
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                  <span>{selectedEntry.exchange}</span>
                  <span>•</span>
                  <span>{selectedEntry.entry_date}</span>
                  <span>•</span>
                  <span>{selectedEntry.model_used}</span>
                  <span>•</span>
                  <span>{selectedEntry.tokens_used} tokens</span>
                  <span>•</span>
                  <span>{(selectedEntry.generation_time_ms / 1000).toFixed(1)}s</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {/* History navigation */}
                {history.length > 1 && (
                  <div className="flex items-center gap-1 mr-2">
                    <button
                      onClick={() => setHistoryIndex(Math.min(historyIndex + 1, history.length - 1))}
                      disabled={historyIndex >= history.length - 1}
                      className="rounded px-2 py-1 text-xs text-gray-400 hover:bg-gray-700/50 disabled:opacity-30"
                      title="Older entry"
                    >
                      ◀
                    </button>
                    <span className="text-xs text-gray-500">
                      {historyIndex + 1}/{history.length}
                    </span>
                    <button
                      onClick={() => setHistoryIndex(Math.max(historyIndex - 1, 0))}
                      disabled={historyIndex <= 0}
                      className="rounded px-2 py-1 text-xs text-gray-400 hover:bg-gray-700/50 disabled:opacity-30"
                      title="Newer entry"
                    >
                      ▶
                    </button>
                  </div>
                )}
                <button
                  onClick={() => handleGenerateSingle(selectedEntry.symbol)}
                  disabled={generatingSymbol === selectedEntry.symbol}
                  className="rounded-lg bg-blue-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                >
                  {generatingSymbol === selectedEntry.symbol ? (
                    <span className="flex items-center gap-1">
                      <span className="h-3 w-3 animate-spin rounded-full border border-white/30 border-t-white" />
                      Generating...
                    </span>
                  ) : (
                    '🔄 Regenerate'
                  )}
                </button>
              </div>
            </div>

            {/* Stats bar */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
              <StatPill label="Price" value={`$${selectedEntry.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} />
              <StatPill
                label="24h"
                value={`${selectedEntry.change_24h >= 0 ? '+' : ''}${selectedEntry.change_24h.toFixed(2)}`}
                suffix="%"
              />
              <StatPill label="RSI" value={selectedEntry.rsi.toFixed(1)} />
              <StatPill label="MACD" value={selectedEntry.macd_signal} />
              <StatPill label="Trend" value={selectedEntry.ema_trend} />
              <StatPill
                label="Target"
                value={`$${selectedEntry.predicted_target.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
              />
            </div>

            {/* Support / Resistance levels */}
            {(selectedEntry.support_level > 0 || selectedEntry.resistance_level > 0) && (
              <div className="flex gap-4 text-xs">
                {selectedEntry.support_level > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Support:</span>
                    <span className="font-medium text-green-400">
                      ${selectedEntry.support_level.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </span>
                  </div>
                )}
                {selectedEntry.resistance_level > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Resistance:</span>
                    <span className="font-medium text-red-400">
                      ${selectedEntry.resistance_level.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* LLM Assessment Panel */}
            <AssessmentPanel entry={selectedEntry} />

            {/* Narrative sections */}
            <div className="space-y-2">
              <NarrativeSection
                title="Background"
                icon="📖"
                content={selectedEntry.lore}
                defaultOpen={false}
              />
              <NarrativeSection
                title="Stats Summary"
                icon="📊"
                content={selectedEntry.stats_summary}
              />
              <NarrativeSection
                title="Technical Analysis"
                icon="🔬"
                content={selectedEntry.tech_analysis}
              />
              <NarrativeSection
                title="Retrospective"
                icon="🔙"
                content={selectedEntry.retrospective}
              />
              <NarrativeSection
                title="Prediction & Outlook"
                icon="🔮"
                content={selectedEntry.prediction}
              />
            </div>

            {/* Prediction history timeline */}
            {history.length > 1 && (
              <div className="mt-6">
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Prediction Track Record
                </h3>
                <div className="space-y-1">
                  {history.slice(0, 14).map((h, i) => {
                    const isActive = i === historyIndex
                    return (
                      <button
                        key={h.id}
                        onClick={() => setHistoryIndex(i)}
                        className={`flex w-full items-center gap-3 rounded px-3 py-1.5 text-xs transition-colors ${
                          isActive
                            ? 'bg-blue-500/15 text-blue-300'
                            : 'text-gray-400 hover:bg-gray-800/50'
                        }`}
                      >
                        <span className="w-20 text-gray-500">{h.entry_date}</span>
                        <DirectionBadge direction={h.predicted_direction} />
                        <span className="flex-1 text-right font-mono">
                          ${h.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </span>
                        <span className="text-right font-mono text-gray-500">
                          → ${h.predicted_target.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </span>
                        <span className="w-16 text-right">
                          <PredictionResult correct={h.prediction_correct} />
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
