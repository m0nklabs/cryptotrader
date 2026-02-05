import { useState } from 'react'
import { useAiStore } from '../stores/aiStore'
import type { RoleName, SignalAction } from '../api/ai'

/**
 * AI Configuration Panel — Multi-Brain agent management.
 *
 * Provides:
 * - Provider health status overview
 * - Role configuration (enable/disable, weight, model, prompt)
 * - Prompt version management per role
 * - Usage/cost dashboard
 * - Manual evaluation trigger
 *
 * Layout: collapsible sections, dark mode, small fonts (MT4-style).
 */
export function AiConfigPanel() {
  const {
    providers,
    roles,
    selectedRole,
    lastDecision,
    evaluating,
    usage,
    setSelectedRole,
    toggleRoleEnabled,
  } = useAiStore()

  return (
    <div className="flex flex-col gap-3 p-3 text-xs">
      {/* Provider Status */}
      <section>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
          Providers
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {providers.map((p) => (
            <div
              key={p.name}
              className="flex items-center gap-2 rounded bg-zinc-800 px-2 py-1.5"
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  p.healthy ? 'bg-green-500' : 'bg-red-500'
                }`}
              />
              <span className="font-mono text-zinc-300">{p.name}</span>
              <span className="ml-auto text-zinc-500">{p.model}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Role Cards */}
      <section>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
          Agent Roles
        </h3>
        <div className="flex flex-col gap-1.5">
          {roles.map((role) => (
            <RoleCard
              key={role.name}
              role={role}
              selected={selectedRole === role.name}
              onSelect={() => setSelectedRole(role.name)}
              onToggle={() => toggleRoleEnabled(role.name)}
            />
          ))}
        </div>
      </section>

      {/* Consensus Result */}
      {lastDecision && (
        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
            Last Decision
          </h3>
          <ConsensusCard decision={lastDecision} />
        </section>
      )}

      {/* Usage Summary */}
      {usage && (
        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
            Usage
          </h3>
          <div className="rounded bg-zinc-800 px-2 py-1.5 font-mono text-zinc-300">
            <div>Total cost: ${usage.totalCostUsd.toFixed(4)}</div>
            <div>Requests: {usage.totalRequests}</div>
          </div>
        </section>
      )}

      {evaluating && (
        <div className="mt-2 text-center text-zinc-500 animate-pulse">
          Evaluating…
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

type RoleCardProps = {
  role: { name: RoleName; provider: string; model: string; weight: number; enabled: boolean }
  selected: boolean
  onSelect: () => void
  onToggle: () => void
}

function RoleCard({ role, selected, onSelect, onToggle }: RoleCardProps) {
  const roleColors: Record<RoleName, string> = {
    screener: 'border-blue-600',
    tactical: 'border-amber-500',
    fundamental: 'border-purple-500',
    strategist: 'border-red-500',
  }

  return (
    <div
      className={`flex items-center gap-2 rounded border px-2 py-1.5 cursor-pointer transition-colors ${
        roleColors[role.name] || 'border-zinc-700'
      } ${selected ? 'bg-zinc-700' : 'bg-zinc-800 hover:bg-zinc-750'}`}
      onClick={onSelect}
    >
      <button
        className={`h-3 w-3 rounded-sm border ${
          role.enabled
            ? 'border-green-500 bg-green-500/30'
            : 'border-zinc-600 bg-transparent'
        }`}
        onClick={(e) => {
          e.stopPropagation()
          onToggle()
        }}
      />
      <span className="font-semibold text-zinc-200 capitalize">{role.name}</span>
      <span className="text-zinc-500">→</span>
      <span className="font-mono text-zinc-400">{role.model}</span>
      <span className="ml-auto text-zinc-500">w={role.weight}</span>
    </div>
  )
}

function ConsensusCard({ decision }: { decision: { finalAction: SignalAction; finalConfidence: number; reasoning: string; totalCostUsd: number; totalLatencyMs: number } }) {
  const actionColor: Record<SignalAction, string> = {
    BUY: 'text-green-400',
    SELL: 'text-red-400',
    NEUTRAL: 'text-zinc-400',
    VETO: 'text-orange-400',
  }

  return (
    <div className="rounded bg-zinc-800 px-2 py-1.5">
      <div className="flex items-center gap-2">
        <span className={`font-bold ${actionColor[decision.finalAction]}`}>
          {decision.finalAction}
        </span>
        <span className="text-zinc-400">
          conf={decision.finalConfidence.toFixed(2)}
        </span>
        <span className="ml-auto text-zinc-500 font-mono">
          ${decision.totalCostUsd.toFixed(4)} / {decision.totalLatencyMs.toFixed(0)}ms
        </span>
      </div>
      <div className="mt-1 text-zinc-500 leading-tight">{decision.reasoning}</div>
    </div>
  )
}
