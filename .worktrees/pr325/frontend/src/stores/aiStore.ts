import { create } from 'zustand'
import type { RoleName, ProviderName, RoleConfig, ProviderStatus, ConsensusDecision, UsageSummary } from '../api/ai'

type AiState = {
  // Provider status
  providers: ProviderStatus[]
  providersLoading: boolean

  // Role configurations
  roles: RoleConfig[]
  rolesLoading: boolean
  selectedRole: RoleName | null

  // Last evaluation result
  lastDecision: ConsensusDecision | null
  evaluating: boolean

  // Usage tracking
  usage: UsageSummary | null

  // Actions
  setProviders: (providers: ProviderStatus[]) => void
  setProvidersLoading: (loading: boolean) => void
  setRoles: (roles: RoleConfig[]) => void
  setRolesLoading: (loading: boolean) => void
  setSelectedRole: (role: RoleName | null) => void
  setLastDecision: (decision: ConsensusDecision | null) => void
  setEvaluating: (evaluating: boolean) => void
  setUsage: (usage: UsageSummary | null) => void
  toggleRoleEnabled: (role: RoleName) => void
  updateRoleWeight: (role: RoleName, weight: number) => void
}

export const useAiStore = create<AiState>((set) => ({
  providers: [],
  providersLoading: false,
  roles: [],
  rolesLoading: false,
  selectedRole: null,
  lastDecision: null,
  evaluating: false,
  usage: null,

  setProviders: (providers) => set({ providers }),
  setProvidersLoading: (providersLoading) => set({ providersLoading }),
  setRoles: (roles) => set({ roles }),
  setRolesLoading: (rolesLoading) => set({ rolesLoading }),
  setSelectedRole: (selectedRole) => set({ selectedRole }),
  setLastDecision: (lastDecision) => set({ lastDecision }),
  setEvaluating: (evaluating) => set({ evaluating }),
  setUsage: (usage) => set({ usage }),

  toggleRoleEnabled: (roleName) =>
    set((state) => ({
      roles: state.roles.map((r) =>
        r.name === roleName ? { ...r, enabled: !r.enabled } : r,
      ),
    })),

  updateRoleWeight: (roleName, weight) =>
    set((state) => ({
      roles: state.roles.map((r) =>
        r.name === roleName ? { ...r, weight } : r,
      ),
    })),
}))
