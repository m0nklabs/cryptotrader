/**
 * Walk-Forward Panel Tests
 * ========================
 *
 * Regression tests for the bug in #433 — the backend walk-forward result
 * was being silently dropped by the frontend type contract and never
 * surfaced in the UI. Acceptance criteria require three test fixtures:
 * zero-fold (insufficient), failed-validation, and passing-validation.
 *
 * The panel itself is the unit under test. We render it directly with
 * synthetic `WalkForwardResult` payloads so this is a pure, fast
 * component test — no API mocking required.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import WalkForwardPanel, {
  classifyWalkForward,
} from '../components/WalkForwardPanel'
import type { WalkForwardResult, WalkForwardFold } from '../api/backtest'
import { MIN_WALK_FORWARD_FOLDS } from '../api/backtest'

// Sanity check: matches WalkForwardConfig.min_folds in core/strategy_eval/walk_forward.py.
expect(MIN_WALK_FORWARD_FOLDS).toBe(5)

const baseFold: WalkForwardFold = {
  train_start: '2024-01-01T00:00:00+00:00',
  train_end: '2024-04-01T00:00:00+00:00',
  test_start: '2024-04-01T00:00:00+00:00',
  test_end: '2024-05-01T00:00:00+00:00',
  train_return: 0.10,
  test_return: 0.05,
  test_sharpe: 1.2,
  test_max_dd: 0.05,
  test_win_rate: 0.55,
  test_trades: 12,
  oos_decay: 0.5,
}

function makePassed(nFolds: number = 6): WalkForwardResult {
  const folds: WalkForwardFold[] = Array.from({ length: nFolds }, (_, i) => ({
    ...baseFold,
    train_return: 0.10 + i * 0.005,
    test_return: 0.05 + i * 0.002,
    oos_decay: 0.8,
  }))
  return {
    n_folds: nFolds,
    mean_train_return: 0.105,
    mean_test_return: 0.052,
    mean_oos_decay: 0.8,
    in_sample_consistency: 0.6,
    oos_significant: true,
    oos_sharpe: 1.4,
    oos_max_dd: 0.06,
    oos_win_rate: 0.55,
    overfitting_risk: 'low',
    folds,
  }
}

function makeFailedInsufficientFolds(): WalkForwardResult {
  // 3 folds: below MIN_WALK_FORWARD_FOLDS, but otherwise OK.
  const folds: WalkForwardFold[] = Array.from({ length: 3 }, () => ({
    ...baseFold,
    oos_decay: 0.8,
  }))
  return {
    n_folds: 3,
    mean_train_return: 0.10,
    mean_test_return: 0.05,
    mean_oos_decay: 0.5,
    in_sample_consistency: 0.6,
    oos_significant: true,
    oos_sharpe: 1.2,
    oos_max_dd: 0.06,
    oos_win_rate: 0.55,
    overfitting_risk: 'medium',
    folds,
  }
}

function makeFailedOverfitting(): WalkForwardResult {
  const folds: WalkForwardFold[] = Array.from({ length: 6 }, (_, i) => ({
    ...baseFold,
    train_return: 0.20,
    test_return: 0.02,
    oos_decay: 0.1,
  }))
  return {
    n_folds: 6,
    mean_train_return: 0.20,
    mean_test_return: 0.02,
    mean_oos_decay: 0.1,
    in_sample_consistency: 0.2,
    oos_significant: false,
    oos_sharpe: 0.4,
    oos_max_dd: 0.15,
    oos_win_rate: 0.45,
    overfitting_risk: 'high',
    folds,
  }
}

function makeZeroFold(): WalkForwardResult {
  return {
    n_folds: 0,
    mean_train_return: 0,
    mean_test_return: 0,
    mean_oos_decay: 0,
    in_sample_consistency: 0,
    oos_significant: false,
    oos_sharpe: 0,
    oos_max_dd: 0,
    oos_win_rate: 0,
    overfitting_risk: 'high',
    folds: [],
  }
}

describe('classifyWalkForward', () => {
  it('returns insufficient when there are zero folds', () => {
    expect(classifyWalkForward(makeZeroFold())).toBe('insufficient')
  })

  it('returns failed when folds are below min_folds', () => {
    expect(classifyWalkForward(makeFailedInsufficientFolds())).toBe('failed')
  })

  it('returns failed when OOS is not significant', () => {
    expect(classifyWalkForward(makeFailedOverfitting())).toBe('failed')
  })

  it('returns passed when all gates pass', () => {
    expect(classifyWalkForward(makePassed())).toBe('passed')
  })
})

describe('WalkForwardPanel rendering', () => {
  it('blocks promotion and shows zero-fold error when no folds were produced', () => {
    render(<WalkForwardPanel walkForward={makeZeroFold()} />)

    // Bug regression: previously, no walk-forward UI existed and zero-fold
    // results were silently invisible. The panel must surface this state.
    const banner = screen.getByTestId('walk-forward-insufficient')
    expect(banner).toBeInTheDocument()
    expect(banner).toHaveAttribute('role', 'alert')
    expect(banner).toHaveTextContent(/Insufficient Data/i)
    expect(banner).toHaveTextContent(/0 folds/)
    expect(banner).toHaveTextContent(/Promotion is blocked/i)
  })

  it('renders a failed-validation banner when folds < min_folds and explains the gap', () => {
    render(
      <WalkForwardPanel walkForward={makeFailedInsufficientFolds()} />
    )

    const banner = screen.getByTestId('walk-forward-failed')
    expect(banner).toBeInTheDocument()
    expect(banner).toHaveAttribute('role', 'alert')
    expect(banner).toHaveTextContent(/Validation did not pass/i)
    // Must explicitly call out the min-folds gap so the operator sees why
    // promotion is blocked.
    expect(banner).toHaveTextContent(
      new RegExp(`minimum ${MIN_WALK_FORWARD_FOLDS}`, 'i')
    )
    expect(banner).toHaveTextContent(/Promotion is blocked/i)
  })

  it('renders a passed banner and surfaces OOS metrics when validation passes', () => {
    render(<WalkForwardPanel walkForward={makePassed()} />)

    const banner = screen.getByTestId('walk-forward-passed')
    expect(banner).toBeInTheDocument()
    expect(banner).toHaveTextContent(/Passed/i)
    // OOS metric labels must be present so operators see evidence.
    expect(screen.getByText(/Mean Test Return \(OOS\)/)).toBeInTheDocument()
    expect(screen.getByText(/Mean OOS Decay/)).toBeInTheDocument()
    expect(screen.getByText(/OOS Sharpe/)).toBeInTheDocument()
    expect(screen.getByText(/OOS Max Drawdown/)).toBeInTheDocument()
    expect(screen.getByText(/OOS Win Rate/)).toBeInTheDocument()
    expect(screen.getByText(/In-Sample Consistency/)).toBeInTheDocument()
    expect(screen.getByText(/Overfitting Risk/)).toBeInTheDocument()
  })

  it('surfaces overfitting risk as a high-risk badge when validation failed due to overfitting', () => {
    render(<WalkForwardPanel walkForward={makeFailedOverfitting()} />)

    expect(screen.getByTestId('walk-forward-failed')).toBeInTheDocument()
    // The High risk badge must be present (visually distinct from a clean PASS).
    expect(screen.getByText(/^High$/)).toBeInTheDocument()
    expect(screen.getByText(/high \(mean OOS decay is far from 1\.0\)/i)).toBeInTheDocument()
  })
})
