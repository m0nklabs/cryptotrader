import { DEFAULT_API_TIMEOUT_MS } from '../lib/apiConfig'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ProviderName = 'deepseek' | 'openai' | 'xai' | 'ollama' | 'google'
export type RoleName = 'screener' | 'tactical' | 'fundamental' | 'strategist'
export type SignalAction = 'BUY' | 'SELL' | 'NEUTRAL' | 'VETO'

export type ProviderStatus = {
  name: ProviderName
  healthy: boolean
  model: string
  lastChecked: string
}

export type RoleConfig = {
  name: RoleName
  provider: ProviderName
  model: string
  systemPromptId: string
  temperature: number
  maxTokens: number
  weight: number
  enabled: boolean
  fallbackProvider: ProviderName | null
  fallbackModel: string | null
}

export type SystemPrompt = {
  id: string
  role: RoleName
  version: number
  content: string
  description: string
  isActive: boolean
  createdAt: string
}

export type RoleVerdict = {
  role: RoleName
  action: SignalAction
  confidence: number
  reasoning: string
  metrics: Record<string, number>
}

export type ConsensusDecision = {
  finalAction: SignalAction
  finalConfidence: number
  verdicts: RoleVerdict[]
  reasoning: string
  vetoedBy: RoleName | null
  totalCostUsd: number
  totalLatencyMs: number
}

export type UsageRecord = {
  role: RoleName
  provider: ProviderName
  model: string
  tokensIn: number
  tokensOut: number
  costUsd: number
  latencyMs: number
  timestamp: string
  symbol: string
  success: boolean
}

export type UsageSummary = {
  totalCostUsd: number
  totalRequests: number
  byRole: Record<RoleName, { cost: number; requests: number; avgLatencyMs: number }>
  byProvider: Record<ProviderName, { cost: number; requests: number }>
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/**
 * Fetch all provider health statuses.
 */
export async function fetchProviderStatus(
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<ProviderStatus[]> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch('/api/ai/providers', { signal: controller.signal })
    if (!response.ok) throw new Error(`Failed to fetch providers: ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Fetch all role configurations.
 */
export async function fetchRoleConfigs(
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<RoleConfig[]> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch('/api/ai/roles', { signal: controller.signal })
    if (!response.ok) throw new Error(`Failed to fetch roles: ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Update a role configuration.
 */
export async function updateRoleConfig(
  role: RoleName,
  config: Partial<RoleConfig>,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<RoleConfig> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`/api/ai/roles/${role}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Failed to update role: ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Fetch all prompt versions for a role.
 */
export async function fetchPrompts(
  role: RoleName,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<SystemPrompt[]> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`/api/ai/prompts/${role}`, { signal: controller.signal })
    if (!response.ok) throw new Error(`Failed to fetch prompts: ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Create a new prompt version.
 */
export async function createPrompt(
  prompt: Omit<SystemPrompt, 'createdAt'>,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<SystemPrompt> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch('/api/ai/prompts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(prompt),
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Failed to create prompt: ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Request a Multi-Brain evaluation for a symbol.
 */
export async function evaluateSymbol(
  symbol: string,
  timeframe: string = '1h',
  roles?: RoleName[],
  timeoutMs: number = 120_000, // longer timeout for multi-agent
): Promise<ConsensusDecision> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const params = new URLSearchParams({ symbol, timeframe })
    if (roles) params.set('roles', roles.join(','))

    const response = await fetch(`/api/ai/evaluate?${params}`, { signal: controller.signal })
    if (!response.ok) throw new Error(`Evaluation failed: ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Fetch usage/cost summary.
 */
export async function fetchUsageSummary(
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<UsageSummary> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch('/api/ai/usage', { signal: controller.signal })
    if (!response.ok) throw new Error(`Failed to fetch usage: ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}
