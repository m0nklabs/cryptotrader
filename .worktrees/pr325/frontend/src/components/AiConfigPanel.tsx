import { useState } from 'react'
import { useProviders, useRoles, useUsage, useUpdateRole, useBudgetStatus, usePrompts, useActivatePrompt } from '../hooks/useAi'
import { useAiStore } from '../stores/aiStore'
import type { RoleName, SignalAction, ProviderStatus, RoleConfig, SystemPrompt, ConsensusDecision } from '../api/ai'

/**
 * AI Configuration Panel — Multi-Brain agent management.
 *
 * Provides:
 * - Provider health status overview (auto-refresh 30s)
 * - Role configuration (enable/disable, weight, model, prompt)
 * - Prompt version management per role
 * - Usage/cost dashboard with budget status
 *
 * Layout: collapsible sections, dark mode, small fonts (MT4-style).
 */
export function AiConfigPanel() {
  const {
    selectedRole,
    lastDecision,
    evaluating,
    setSelectedRole,
  } = useAiStore()

  // Data fetching via React Query hooks
  const { data: providers = [], isLoading: providersLoading } = useProviders()
  const { data: roles = [], isLoading: rolesLoading } = useRoles()
  const { data: usage } = useUsage()
  const { data: budget } = useBudgetStatus('global')
  const { data: prompts = [] } = usePrompts(selectedRole)

  const updateRole = useUpdateRole()
  const activatePromptMut = useActivatePrompt()

  const handleToggleEnabled = (role: RoleConfig) => {
    updateRole.mutate({ role: role.name, config: { enabled: !role.enabled } })
  }

  const handleWeightChange = (role: RoleConfig, weight: number) => {
    updateRole.mutate({ role: role.name, config: { weight } })
  }

  const handleActivatePrompt = (promptId: string) => {
    activatePromptMut.mutate(promptId)
  }

  return (
    <div className="flex flex-col gap-3 p-3 text-xs">
      {/* Provider Status */}
      <section>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
          Providers
        </h3>
        {providersLoading ? (
          <div className="text-zinc-500 animate-pulse">Loading providers…</div>
        ) : providers.length === 0 ? (
          <div className="text-zinc-500">No providers configured</div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {providers.map((p: ProviderStatus) => (
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
        )}
      </section>

      {/* Role Cards */}
      <section>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
          Agent Roles
        </h3>
        {rolesLoading ? (
          <div className="text-zinc-500 animate-pulse">Loading roles…</div>
        ) : roles.length === 0 ? (
          <div className="text-zinc-500">No roles configured</div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {roles.map((role: RoleConfig) => (
              <RoleCard
                key={role.name}
                role={role}
                selected={selectedRole === role.name}
                onSelect={() => setSelectedRole(role.name)}
                onToggle={() => handleToggleEnabled(role)}
                onWeightChange={(w) => handleWeightChange(role, w)}
                saving={updateRole.isPending}
              />
            ))}
          </div>
        )}
      </section>

      {/* Prompts for selected role */}
      {selectedRole && prompts.length > 0 && (
        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
            Prompts — {selectedRole}
          </h3>
          <div className="flex flex-col gap-1">
            {prompts.map((prompt: SystemPrompt) => (
              <div
                key={prompt.id}
                className={`flex items-center gap-2 rounded px-2 py-1.5 text-[10px] ${
                  prompt.isActive
                    ? 'bg-blue-900/30 border border-blue-500/50'
                    : 'bg-zinc-800 border border-zinc-700'
                }`}
              >
                <span className="font-mono text-zinc-300">v{prompt.version}</span>
                <span className="text-zinc-400 truncate flex-1">{prompt.description || 'No description'}</span>
                {prompt.isActive ? (
                  <span className="text-blue-400 text-[9px]">ACTIVE</span>
                ) : (
                  <button
                    onClick={() => handleActivatePrompt(prompt.id)}
                    disabled={activatePromptMut.isPending}
                    className="text-zinc-500 hover:text-blue-400 text-[9px] underline"
                  >
                    Activate
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Budget Status */}
      {budget && (
        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
            Budget
          </h3>
          <div className="rounded bg-zinc-800 px-2 py-1.5 font-mono text-zinc-300">
            <div className="flex justify-between">
              <span>Daily</span>
              <span className={budget.dailyExceeded ? 'text-red-400' : ''}>
                ${budget.dailySpent.toFixed(4)} / ${budget.dailyLimit.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Monthly</span>
              <span className={budget.monthlyExceeded ? 'text-red-400' : ''}>
                ${budget.monthlySpent.toFixed(4)} / ${budget.monthlyLimit.toFixed(2)}
              </span>
            </div>
          </div>
        </section>
      )}

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
  role: RoleConfig
  selected: boolean
  onSelect: () => void
  onToggle: () => void
  onWeightChange: (weight: number) => void
  saving: boolean
}

function RoleCard({ role, selected, onSelect, onToggle, onWeightChange, saving }: RoleCardProps) {
  const [editingWeight, setEditingWeight] = useState(false)
  const [weightInput, setWeightInput] = useState(String(role.weight))

  const roleColors: Record<RoleName, string> = {
    screener: 'border-blue-600',
    tactical: 'border-amber-500',
    fundamental: 'border-purple-500',
    strategist: 'border-red-500',
  }

  const handleWeightSubmit = () => {
    const w = parseFloat(weightInput)
    if (!isNaN(w) && w >= 0 && w <= 1) {
      onWeightChange(w)
    }
    setEditingWeight(false)
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
        disabled={saving}
      />
      <span className="font-semibold text-zinc-200 capitalize">{role.name}</span>
      <span className="text-zinc-500">→</span>
      <span className="font-mono text-zinc-400">{role.model}</span>
      {editingWeight ? (
        <input
          type="number"
          step="0.05"
          min="0"
          max="1"
          value={weightInput}
          onChange={(e) => setWeightInput(e.target.value)}
          onBlur={handleWeightSubmit}
          onKeyDown={(e) => e.key === 'Enter' && handleWeightSubmit()}
          onClick={(e) => e.stopPropagation()}
          className="ml-auto w-14 rounded bg-zinc-900 border border-zinc-600 px-1 py-0.5 text-[10px] font-mono text-zinc-300 focus:outline-none focus:border-blue-500"
          autoFocus
        />
      ) : (
        <span
          className="ml-auto text-zinc-500 cursor-text hover:text-zinc-300"
          onClick={(e) => {
            e.stopPropagation()
            setWeightInput(String(role.weight))
            setEditingWeight(true)
          }}
        >
          w={role.weight}
        </span>
      )}
    </div>
  )
}

function ConsensusCard({ decision }: { decision: ConsensusDecision }) {
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
