import { useState } from 'react'
import { evaluateSymbol } from '../api/ai'
import { useAiStore } from '../stores/aiStore'
import type { SignalAction, RoleName, ConsensusDecision } from '../api/ai'

/**
 * AI Evaluation Panel — Manual Multi-Brain evaluation trigger.
 *
 * Provides:
 * - Symbol input + timeframe selector
 * - "Evaluate" button with loading state
 * - Consensus decision display (action, confidence, reasoning, cost/latency)
 * - Per-role verdict breakdown
 * - Error handling with retry
 *
 * Minimal MVP: no filters, no complex settings.
 */
export function AiEvaluationPanel() {
  const { setLastDecision, setEvaluating } = useAiStore()

  const [symbol, setSymbol] = useState('BTC/USDT')
  const [timeframe, setTimeframe] = useState('1h')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [decision, setDecision] = useState<ConsensusDecision | null>(null)

  const handleEvaluate = async () => {
    if (!symbol.trim()) {
      setError('Symbol is required')
      return
    }

    setLoading(true)
    setEvaluating(true)
    setError(null)
    setDecision(null)

    try {
      const result = await evaluateSymbol(symbol.trim(), timeframe)
      setDecision(result)
      setLastDecision(result)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Evaluation failed'
      setError(message)
    } finally {
      setLoading(false)
      setEvaluating(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 p-3 text-xs">
      {/* Input Form */}
      <section>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
          Evaluate Symbol
        </h3>
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Symbol (e.g., BTC/USDT)"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="flex-1 rounded bg-zinc-800 px-2 py-1.5 text-zinc-300 border border-zinc-700 focus:border-blue-500 focus:outline-none"
              disabled={loading}
            />
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="rounded bg-zinc-800 px-2 py-1.5 text-zinc-300 border border-zinc-700 focus:border-blue-500 focus:outline-none"
              disabled={loading}
            >
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </div>
          <button
            onClick={handleEvaluate}
            disabled={loading}
            className={`rounded px-3 py-1.5 font-semibold transition-colors ${
              loading
                ? 'bg-zinc-700 text-zinc-500 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {loading ? 'Evaluating…' : 'Evaluate'}
          </button>
        </div>
      </section>

      {/* Loading State */}
      {loading && (
        <div className="text-center text-zinc-400 animate-pulse">
          Running Multi-Brain evaluation…
        </div>
      )}

      {/* Error Display */}
      {error && (
        <section>
          <div className="rounded bg-red-900/20 border border-red-500/50 px-3 py-2">
            <div className="font-semibold text-red-400 mb-1">Error</div>
            <div className="text-zinc-300">{error}</div>
            <button
              onClick={handleEvaluate}
              className="mt-2 text-xs text-red-400 hover:text-red-300 underline"
            >
              Retry
            </button>
          </div>
        </section>
      )}

      {/* Consensus Decision */}
      {decision && (
        <>
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
              Consensus Decision
            </h3>
            <ConsensusCard decision={decision} />
          </section>

          {/* Per-Role Verdicts */}
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
              Role Verdicts ({decision.verdicts.length})
            </h3>
            <div className="flex flex-col gap-1.5">
              {decision.verdicts.map((verdict, idx) => (
                <VerdictCard key={`${verdict.role}-${idx}`} verdict={verdict} />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConsensusCard({ decision }: { decision: ConsensusDecision }) {
  const actionColor: Record<SignalAction, string> = {
    BUY: 'text-green-400',
    SELL: 'text-red-400',
    NEUTRAL: 'text-zinc-400',
    VETO: 'text-orange-400',
  }

  return (
    <div className="rounded bg-zinc-800 border border-zinc-700 px-3 py-2">
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-lg font-bold ${actionColor[decision.finalAction]}`}>
          {decision.finalAction}
        </span>
        <span className="text-zinc-400">
          confidence: {(decision.finalConfidence * 100).toFixed(1)}%
        </span>
        {decision.vetoedBy && (
          <span className="ml-auto text-orange-400 text-xs">
            VETOED by {decision.vetoedBy}
          </span>
        )}
      </div>
      <div className="text-zinc-300 leading-tight mb-2">{decision.reasoning}</div>
      <div className="flex items-center gap-3 text-[10px] text-zinc-500 font-mono">
        <span>cost: ${decision.totalCostUsd.toFixed(4)}</span>
        <span>latency: {decision.totalLatencyMs.toFixed(0)}ms</span>
      </div>
    </div>
  )
}

function VerdictCard({ verdict }: { verdict: { role: RoleName; action: SignalAction; confidence: number; reasoning: string } }) {
  const roleColors: Record<RoleName, string> = {
    screener: 'border-blue-600',
    tactical: 'border-amber-500',
    fundamental: 'border-purple-500',
    strategist: 'border-red-500',
  }

  const actionColor: Record<SignalAction, string> = {
    BUY: 'text-green-400',
    SELL: 'text-red-400',
    NEUTRAL: 'text-zinc-400',
    VETO: 'text-orange-400',
  }

  return (
    <div
      className={`rounded border ${roleColors[verdict.role]} bg-zinc-800 px-2 py-1.5`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="font-semibold text-zinc-200 capitalize">{verdict.role}</span>
        <span className="text-zinc-600">→</span>
        <span className={`font-bold ${actionColor[verdict.action]}`}>
          {verdict.action}
        </span>
        <span className="ml-auto text-zinc-500 text-[10px]">
          conf={(verdict.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <div className="text-zinc-400 leading-tight text-[10px]">{verdict.reasoning}</div>
    </div>
  )
}
