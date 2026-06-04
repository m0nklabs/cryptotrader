import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchProviderStatus,
  fetchRoleConfigs,
  fetchUsageSummary,
  fetchBudgetStatus,
  fetchDecisions,
  evaluateSymbol,
  updateRoleConfig,
  activatePrompt,
  fetchPrompts,
} from '../api/ai'
import type {
  ProviderStatus,
  RoleConfig,
  UsageSummary,
  BudgetStatus,
  ConsensusDecision,
  RoleName,
  EvaluationRequest,
  SystemPrompt,
} from '../api/ai'
import { useAiStore } from '../stores/aiStore'

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const aiKeys = {
  providers: ['ai', 'providers'] as const,
  roles: ['ai', 'roles'] as const,
  usage: ['ai', 'usage'] as const,
  budget: (scope: string) => ['ai', 'budget', scope] as const,
  decisions: (params?: { symbol?: string; limit?: number }) =>
    ['ai', 'decisions', params] as const,
  prompts: (role: RoleName) => ['ai', 'prompts', role] as const,
}

// ---------------------------------------------------------------------------
// Provider health
// ---------------------------------------------------------------------------

/** Fetch provider health with 30s auto-refresh. Syncs to Zustand store. */
export function useProviders() {
  const { setProviders, setProvidersLoading } = useAiStore()

  return useQuery<ProviderStatus[]>({
    queryKey: aiKeys.providers,
    queryFn: () => fetchProviderStatus(),
    refetchInterval: 30_000,
    retry: 2,
    select: (data) => {
      setProviders(data)
      setProvidersLoading(false)
      return data
    },
    placeholderData: [],
  })
}

// ---------------------------------------------------------------------------
// Role configs
// ---------------------------------------------------------------------------

/** Fetch role configurations. Syncs to Zustand store. */
export function useRoles() {
  const { setRoles, setRolesLoading } = useAiStore()

  return useQuery<RoleConfig[]>({
    queryKey: aiKeys.roles,
    queryFn: () => fetchRoleConfigs(),
    retry: 2,
    select: (data) => {
      setRoles(data)
      setRolesLoading(false)
      return data
    },
    placeholderData: [],
  })
}

/** Mutation: update a role config on the backend, then invalidate cache. */
export function useUpdateRole() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ role, config }: { role: RoleName; config: Partial<RoleConfig> }) =>
      updateRoleConfig(role, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.roles })
    },
  })
}

// ---------------------------------------------------------------------------
// Evaluation
// ---------------------------------------------------------------------------

/** Mutation: trigger a Multi-Brain evaluation. */
export function useEvaluate() {
  const { setEvaluating, setLastDecision } = useAiStore()
  const queryClient = useQueryClient()

  return useMutation<ConsensusDecision, Error, EvaluationRequest>({
    mutationFn: (request) => {
      setEvaluating(true)
      return evaluateSymbol(request)
    },
    onSuccess: (data) => {
      setLastDecision(data)
      // Refresh usage stats after eval
      queryClient.invalidateQueries({ queryKey: aiKeys.usage })
    },
    onSettled: () => {
      setEvaluating(false)
    },
  })
}

// ---------------------------------------------------------------------------
// Decisions history
// ---------------------------------------------------------------------------

/** Fetch recent AI decisions. */
export function useDecisions(params?: { symbol?: string; action?: string; limit?: number }) {
  return useQuery<ConsensusDecision[]>({
    queryKey: aiKeys.decisions(params),
    queryFn: () => fetchDecisions(params),
    retry: 1,
    placeholderData: [],
  })
}

// ---------------------------------------------------------------------------
// Usage & budget
// ---------------------------------------------------------------------------

/** Fetch usage summary. Syncs to Zustand store. */
export function useUsage() {
  const { setUsage } = useAiStore()

  return useQuery<UsageSummary>({
    queryKey: aiKeys.usage,
    queryFn: () => fetchUsageSummary(),
    refetchInterval: 60_000,
    retry: 2,
    select: (data) => {
      setUsage(data)
      return data
    },
  })
}

/** Fetch budget status for a scope. */
export function useBudgetStatus(scope: string = 'global') {
  return useQuery<BudgetStatus>({
    queryKey: aiKeys.budget(scope),
    queryFn: () => fetchBudgetStatus(scope),
    refetchInterval: 60_000,
    retry: 1,
  })
}

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------

/** Fetch prompt versions for a role. */
export function usePrompts(role: RoleName | null) {
  return useQuery<SystemPrompt[]>({
    queryKey: aiKeys.prompts(role!),
    queryFn: () => fetchPrompts(role!),
    enabled: !!role,
    retry: 1,
    placeholderData: [],
  })
}

/** Mutation: activate a prompt version. */
export function useActivatePrompt() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (promptId: string) => activatePrompt(promptId),
    onSuccess: () => {
      // Invalidate all prompt queries
      queryClient.invalidateQueries({ queryKey: ['ai', 'prompts'] })
    },
  })
}
