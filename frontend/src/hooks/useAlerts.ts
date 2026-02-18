/**
 * React Query hooks for alerts API.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  Alert,
  AlertHistory,
  CreateAlertRequest,
  UpdateAlertRequest,
} from '../api/alerts'
import * as alertsApi from '../api/alerts'

/**
 * Hook to list alerts with optional filtering.
 */
export function useAlerts(params?: {
  symbol?: string
  exchange?: string
  enabled_only?: boolean
}) {
  return useQuery({
    queryKey: ['alerts', params],
    queryFn: () => alertsApi.listAlerts(params),
    refetchInterval: 30000, // Refresh every 30 seconds
  })
}

/**
 * Hook to get a specific alert.
 */
export function useAlert(alertId: number | null) {
  return useQuery({
    queryKey: ['alerts', alertId],
    queryFn: () => alertsApi.getAlert(alertId!),
    enabled: alertId !== null,
  })
}

/**
 * Hook to get alert history.
 */
export function useAlertHistory(alertId: number | null, limit = 100) {
  return useQuery({
    queryKey: ['alerts', alertId, 'history', limit],
    queryFn: () => alertsApi.getAlertHistory(alertId!, limit),
    enabled: alertId !== null,
  })
}

/**
 * Hook to get all alert history.
 */
export function useAllAlertHistory(limit = 100) {
  return useQuery({
    queryKey: ['alerts', 'history', 'all', limit],
    queryFn: () => alertsApi.getAllAlertHistory(limit),
  })
}

/**
 * Hook to create an alert.
 */
export function useCreateAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: CreateAlertRequest) => alertsApi.createAlert(request),
    onSuccess: () => {
      // Invalidate all alerts queries
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

/**
 * Hook to update an alert.
 */
export function useUpdateAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ alertId, request }: { alertId: number; request: UpdateAlertRequest }) =>
      alertsApi.updateAlert(alertId, request),
    onSuccess: (_, { alertId }) => {
      // Invalidate the specific alert and list queries
      queryClient.invalidateQueries({ queryKey: ['alerts', alertId] })
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

/**
 * Hook to delete an alert.
 */
export function useDeleteAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (alertId: number) => alertsApi.deleteAlert(alertId),
    onSuccess: () => {
      // Invalidate all alerts queries
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}
