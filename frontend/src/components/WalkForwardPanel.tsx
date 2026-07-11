/**
 * Walk-Forward Validation Panel
 * ==============================
 *
 * Renders the OOS validation result returned by `POST /backtest/run`.
 *
 * IMPORTANT: this component never returns a "go live" verdict on its own.
 * Operators must NOT promote a strategy based on the gross backtest alone —
 * the OOS gate below determines whether validation is meaningful at all.
 */

import type { WalkForwardResult } from '../api/backtest'
import { MIN_WALK_FORWARD_FOLDS } from '../api/backtest'

type Props = {
  walkForward: WalkForwardResult
}

const pct = (val: number) => `${(val * 100).toFixed(2)}%`

const fmtSignedPct = (val: number) => {
  const sign = val > 0 ? '+' : val < 0 ? '' : ''
  return `${sign}${pct(val)}`
}

const RISK_STYLES: Record<WalkForwardResult['overfitting_risk'], string> = {
  low: 'bg-green-900/30 text-green-400 border-green-700',
  medium: 'bg-yellow-900/30 text-yellow-400 border-yellow-700',
  high: 'bg-red-900/30 text-red-400 border-red-700',
}

const RISK_LABEL: Record<WalkForwardResult['overfitting_risk'], string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
}

/**
 * Classify the validation outcome so the rest of the UI can branch on it.
 *
 * - `insufficient`: zero folds (no test windows produced) — invalid by
 *   construction; the strategy has *not* been validated.
 * - `failed`: at least one fold ran, but the result is statistically
 *   meaningless (below `MIN_WALK_FORWARD_FOLDS` folds, not significant, or
 *   OOS decay is far from 1.0).
 * - `passed`: sufficient folds, OOS returns significantly > 0, and the
 *   overfitting risk is acceptable.
 */
export type WalkForwardVerdict = 'insufficient' | 'failed' | 'passed'

export function classifyWalkForward(wf: WalkForwardResult): WalkForwardVerdict {
  if (wf.n_folds <= 0) return 'insufficient'
  if (wf.n_folds < MIN_WALK_FORWARD_FOLDS) return 'failed'
  if (!wf.oos_significant) return 'failed'
  // OOS decay: 1.0 means OOS ≈ in-sample; <0.4 is the backend's "high" risk.
  if (wf.overfitting_risk === 'high') return 'failed'
  return 'passed'
}

export default function WalkForwardPanel({ walkForward: wf }: Props) {
  const verdict = classifyWalkForward(wf)

  if (verdict === 'insufficient') {
    return (
      <div
        role="alert"
        data-testid="walk-forward-insufficient"
        className="bg-[#1a1a2e] p-4 rounded border border-red-700"
      >
        <h2 className="text-lg font-semibold mb-2 text-red-400">
          Walk-Forward Validation: Insufficient Data
        </h2>
        <p className="text-sm text-zinc-300">
          Backtest produced <strong className="text-red-400">0 folds</strong>.
          The selected date range is too short for the strategy to be
          evaluated out-of-sample. Extend the date range or reduce the
          walk-forward window before relying on this result.
        </p>
        <p className="mt-3 text-xs text-zinc-500">
          A positive in-sample backtest is <strong>not evidence</strong> of
          edge. Promotion is blocked.
        </p>
      </div>
    )
  }

  if (verdict === 'failed') {
    return (
      <div
        role="alert"
        data-testid="walk-forward-failed"
        className="bg-[#1a1a2e] p-4 rounded border border-yellow-700"
      >
        <h2 className="text-lg font-semibold mb-2 text-yellow-400">
          Walk-Forward Validation: Failed
        </h2>
        <p className="text-sm text-zinc-300 mb-3">
          Validation did not pass. {wf.n_folds} fold{wf.n_folds === 1 ? '' : 's'}
          {' '}produced (minimum {MIN_WALK_FORWARD_FOLDS} required).
          {!wf.oos_significant &&
            ' Out-of-sample returns are not statistically significant.'}
          {wf.overfitting_risk === 'high' &&
            ' Overfitting risk is high (mean OOS decay is far from 1.0).'}
        </p>
        <WalkForwardMetrics wf={wf} />
        <p className="mt-3 text-xs text-zinc-500">
          Promotion is blocked until the strategy passes all walk-forward
          gates.
        </p>
      </div>
    )
  }

  return (
    <div
      data-testid="walk-forward-passed"
      className="bg-[#1a1a2e] p-4 rounded border border-green-700"
    >
      <h2 className="text-lg font-semibold mb-2 text-green-400">
        Walk-Forward Validation: Passed
      </h2>
      <p className="text-sm text-zinc-300 mb-3">
        {wf.n_folds} folds, out-of-sample returns statistically significant,
        overfitting risk {RISK_LABEL[wf.overfitting_risk].toLowerCase()}.
      </p>
      <WalkForwardMetrics wf={wf} />
    </div>
  )
}

function WalkForwardMetrics({ wf }: { wf: WalkForwardResult }) {
  return (
    <>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Metric label="Folds" value={String(wf.n_folds)} />
        <Metric
          label="OOS Significant"
          value={wf.oos_significant ? 'Yes' : 'No'}
          tone={wf.oos_significant ? 'positive' : 'negative'}
        />
        <div className="bg-[#0f0f1e] p-3 rounded border border-zinc-700">
          <div className="text-xs text-zinc-400 mb-1">Overfitting Risk</div>
          <div
            className={`inline-block px-2 py-0.5 rounded text-sm font-medium border ${RISK_STYLES[wf.overfitting_risk]}`}
          >
            {RISK_LABEL[wf.overfitting_risk]}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3 mb-3">
        <Metric
          label="Mean Train Return"
          value={fmtSignedPct(wf.mean_train_return)}
        />
        <Metric
          label="Mean Test Return (OOS)"
          value={fmtSignedPct(wf.mean_test_return)}
          tone={wf.mean_test_return >= 0 ? 'positive' : 'negative'}
        />
        <Metric
          label="Mean OOS Decay"
          value={wf.mean_oos_decay.toFixed(3)}
          tone={
            wf.mean_oos_decay >= 0.7
              ? 'positive'
              : wf.mean_oos_decay >= 0.4
                ? 'neutral'
                : 'negative'
          }
        />
        <Metric
          label="In-Sample Consistency"
          value={wf.in_sample_consistency.toFixed(3)}
        />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Metric label="OOS Sharpe" value={wf.oos_sharpe.toFixed(3)} />
        <Metric
          label="OOS Max Drawdown"
          value={pct(wf.oos_max_dd)}
          tone="negative"
        />
        <Metric
          label="OOS Win Rate"
          value={pct(wf.oos_win_rate)}
          tone={wf.oos_win_rate >= 0.5 ? 'positive' : 'neutral'}
        />
      </div>

      {wf.folds.length > 0 && (
        <details className="mt-3">
          <summary className="text-xs text-zinc-400 cursor-pointer hover:text-zinc-200">
            Per-fold details ({wf.folds.length})
          </summary>
          <div className="mt-2 bg-[#0f0f1e] rounded border border-zinc-700 max-h-48 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[#0f0f1e] border-b border-zinc-700">
                <tr className="text-zinc-400">
                  <th className="text-left p-2">#</th>
                  <th className="text-right p-2">Train Ret</th>
                  <th className="text-right p-2">Test Ret</th>
                  <th className="text-right p-2">Test Sharpe</th>
                  <th className="text-right p-2">Test DD</th>
                  <th className="text-right p-2">Win Rate</th>
                  <th className="text-right p-2">Trades</th>
                  <th className="text-right p-2">OOS Decay</th>
                </tr>
              </thead>
              <tbody>
                {wf.folds.map((f, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-zinc-800 hover:bg-[#1a1a2e]"
                  >
                    <td className="p-2 text-zinc-400">{idx + 1}</td>
                    <td className="p-2 text-right text-zinc-300">
                      {fmtSignedPct(f.train_return)}
                    </td>
                    <td
                      className={`p-2 text-right ${f.test_return >= 0 ? 'text-green-400' : 'text-red-400'}`}
                    >
                      {fmtSignedPct(f.test_return)}
                    </td>
                    <td className="p-2 text-right text-zinc-300">
                      {f.test_sharpe.toFixed(2)}
                    </td>
                    <td className="p-2 text-right text-red-400">
                      {pct(f.test_max_dd)}
                    </td>
                    <td className="p-2 text-right text-zinc-300">
                      {pct(f.test_win_rate)}
                    </td>
                    <td className="p-2 text-right text-zinc-300">
                      {f.test_trades}
                    </td>
                    <td className="p-2 text-right text-zinc-300">
                      {f.oos_decay.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </>
  )
}

function Metric({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'positive' | 'negative' | 'neutral'
}) {
  const valueClass =
    tone === 'positive'
      ? 'text-green-400'
      : tone === 'negative'
        ? 'text-red-400'
        : 'text-zinc-100'
  return (
    <div className="bg-[#0f0f1e] p-3 rounded border border-zinc-700">
      <div className="text-xs text-zinc-400 mb-1">{label}</div>
      <div className={`text-lg font-semibold ${valueClass}`}>{value}</div>
    </div>
  )
}
