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
  symbol: string
  timeframe: string
  finalAction: SignalAction
  finalConfidence: number
  verdicts: RoleVerdict[]
  reasoning: string
  vetoedBy: RoleName | null
  totalCostUsd: number
  totalLatencyMs: number
  createdAt: string
}

export type EvaluationRequest = {
  symbol: string
  timeframe?: string
  candles?: Record<string, unknown>[]
  indicators?: Record<string, unknown>
  portfolio?: Record<string, unknown>
  riskLimits?: Record<string, unknown>
  roles?: RoleName[]
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

export type DailyUsage = {
  date: string
  totalCostUsd: number
  totalRequests: number
  totalTokensIn: number
  totalTokensOut: number
}

export type BudgetStatus = {
  scope: string
  dailyLimit: number
  monthlyLimit: number
  dailySpent: number
  monthlySpent: number
  dailyExceeded: boolean
  monthlyExceeded: boolean
  exceeded: boolean
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/** Helper for fetch with abort timeout. */
async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, { ...init, signal: controller.signal })
    return response
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Fetch all provider health statuses.
 */
export async function fetchProviderStatus(
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<ProviderStatus[]> {
  const response = await fetchWithTimeout('/api/ai/providers', {}, timeoutMs)
  if (!response.ok) throw new Error(`Failed to fetch providers: ${response.status}`)
  return await response.json()
}

/**
 * Fetch all role configurations.
 */
export async function fetchRoleConfigs(
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<RoleConfig[]> {
  const response = await fetchWithTimeout('/api/ai/roles', {}, timeoutMs)
  if (!response.ok) throw new Error(`Failed to fetch roles: ${response.status}`)
  return await response.json()
}

/**
 * Update a role configuration.
 */
export async function updateRoleConfig(
  role: RoleName,
  config: Partial<RoleConfig>,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<RoleConfig> {
  const response = await fetchWithTimeout(`/api/ai/roles/${role}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  }, timeoutMs)
  if (!response.ok) throw new Error(`Failed to update role: ${response.status}`)
  return await response.json()
}

/**
 * Fetch all prompt versions for a role.
 */
export async function fetchPrompts(
  role: RoleName,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<SystemPrompt[]> {
  const response = await fetchWithTimeout(`/api/ai/prompts/${role}`, {}, timeoutMs)
  if (!response.ok) throw new Error(`Failed to fetch prompts: ${response.status}`)
  return await response.json()
}

/**
 * Create a new prompt version.
 */
export async function createPrompt(
  prompt: Omit<SystemPrompt, 'createdAt'>,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<SystemPrompt> {
  const response = await fetchWithTimeout('/api/ai/prompts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(prompt),
  }, timeoutMs)
  if (!response.ok) throw new Error(`Failed to create prompt: ${response.status}`)
  return await response.json()
}

/**
 * Activate a specific prompt version.
 */
export async function activatePrompt(
  promptId: string,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<{ status: string }> {
  const response = await fetchWithTimeout(`/api/ai/prompts/${promptId}/activate`, {
    method: 'PUT',
  }, timeoutMs)
  if (!response.ok) throw new Error(`Failed to activate prompt: ${response.status}`)
  return await response.json()
}

/**
 * Request a Multi-Brain evaluation for a symbol (POST — canonical endpoint).
 */
export async function evaluateSymbol(
  request: EvaluationRequest,
  timeoutMs: number = 120_000, // longer timeout for multi-agent
): Promise<ConsensusDecision> {
  const response = await fetchWithTimeout('/api/ai/evaluate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  }, timeoutMs)
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`Evaluation failed (${response.status}): ${detail}`)
  }
  return await response.json()
}

/**
 * Fetch recent AI decisions.
 */
export async function fetchDecisions(
  params?: { symbol?: string; action?: string; limit?: number },
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<ConsensusDecision[]> {
  const searchParams = new URLSearchParams()
  if (params?.symbol) searchParams.set('symbol', params.symbol)
  if (params?.action) searchParams.set('action', params.action)
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const qs = searchParams.toString()
  const url = `/api/ai/decisions${qs ? `?${qs}` : ''}`
  const response = await fetchWithTimeout(url, {}, timeoutMs)
  if (!response.ok) throw new Error(`Failed to fetch decisions: ${response.status}`)
  return await response.json()
}

/**
 * Fetch usage/cost summary.
 */
export async function fetchUsageSummary(
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<UsageSummary> {
  const response = await fetchWithTimeout('/api/ai/usage', {}, timeoutMs)
  if (!response.ok) throw new Error(`Failed to fetch usage: ${response.status}`)
  return await response.json()
}

/**
 * Fetch daily usage breakdown.
 */
export async function fetchDailyUsage(
  days: number = 30,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<DailyUsage[]> {
  const response = await fetchWithTimeout(`/api/ai/usage/daily?days=${days}`, {}, timeoutMs)
  if (!response.ok) throw new Error(`Failed to fetch daily usage: ${response.status}`)
  return await response.json()
}

/**
 * Fetch budget status for a scope (global or role name).
 */
export async function fetchBudgetStatus(
  scope: string = 'global',
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS,
): Promise<BudgetStatus> {
  const response = await fetchWithTimeout(`/api/ai/budget/status?scope=${scope}`, {}, timeoutMs)
  if (!response.ok) throw new Error(`Failed to fetch budget status: ${response.status}`)
  return await response.json()
}
