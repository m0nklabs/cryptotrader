/**
 * Alert management panel - create, view, and manage price/indicator alerts.
 */

import { useState, useEffect } from 'react'
import { useAlerts, useCreateAlert, useDeleteAlert, useUpdateAlert } from '../hooks/useAlerts'
import AlertForm from './AlertForm'
import type { Alert } from '../api/alerts'
import { requestNotificationPermission } from '../lib/notifications'

type ViewMode = 'list' | 'create' | 'history'

export default function AlertManager() {
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [filterSymbol, setFilterSymbol] = useState('')
  const [filterExchange, setFilterExchange] = useState('')
  const [enabledOnly, setEnabledOnly] = useState(false)
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>('default')

  const { data: alertsData, isLoading, error } = useAlerts({
    symbol: filterSymbol || undefined,
    exchange: filterExchange || undefined,
    enabled_only: enabledOnly,
  })

  const createAlert = useCreateAlert()
  const updateAlert = useUpdateAlert()
  const deleteAlert = useDeleteAlert()

  useEffect(() => {
    // Check notification permission on mount
    if ('Notification' in window) {
      setNotificationPermission(Notification.permission)
    }
  }, [])

  const handleRequestNotifications = async () => {
    const permission = await requestNotificationPermission()
    setNotificationPermission(permission)
  }

  const handleCreateAlert = async (request: any) => {
    try {
      await createAlert.mutateAsync(request)
      setViewMode('list')
    } catch (err) {
      console.error('Failed to create alert:', err)
      alert('Failed to create alert. Please try again.')
    }
  }

  const handleToggleAlert = async (alert: Alert) => {
    try {
      await updateAlert.mutateAsync({
        alertId: alert.id,
        request: { enabled: !alert.enabled },
      })
    } catch (err) {
      console.error('Failed to update alert:', err)
    }
  }

  const handleDeleteAlert = async (alertId: number) => {
    if (!confirm('Are you sure you want to delete this alert?')) {
      return
    }

    try {
      await deleteAlert.mutateAsync(alertId)
    } catch (err) {
      console.error('Failed to delete alert:', err)
    }
  }

  const getAlertTypeLabel = (type: string): string => {
    const labels: Record<string, string> = {
      price_above: 'Price Above',
      price_below: 'Price Below',
      rsi_overbought: 'RSI Overbought',
      rsi_oversold: 'RSI Oversold',
      macd_cross_up: 'MACD Bull Cross',
      macd_cross_down: 'MACD Bear Cross',
    }
    return labels[type] || type
  }

  const getAlertIcon = (type: string): string => {
    if (type === 'price_above') return '📈'
    if (type === 'price_below') return '📉'
    if (type === 'rsi_overbought') return '🔴'
    if (type === 'rsi_oversold') return '🟢'
    if (type === 'macd_cross_up') return '⬆️'
    if (type === 'macd_cross_down') return '⬇️'
    return '🔔'
  }

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-white">Alerts</h2>
        <div className="flex gap-2">
          {notificationPermission !== 'granted' && (
            <button
              onClick={handleRequestNotifications}
              className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 text-white rounded text-xs"
            >
              Enable Notifications
            </button>
          )}
          {notificationPermission === 'granted' && (
            <span className="px-2 py-1 bg-green-900/30 text-green-400 rounded text-xs">
              🔔 Notifications On
            </span>
          )}
          <button
            onClick={() => setViewMode(viewMode === 'create' ? 'list' : 'create')}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs"
          >
            {viewMode === 'create' ? 'View Alerts' : '+ New Alert'}
          </button>
        </div>
      </div>

      {/* View Modes */}
      {viewMode === 'create' && (
        <div className="mb-4 p-4 bg-zinc-800 rounded-lg">
          <h3 className="text-sm font-bold text-white mb-3">Create New Alert</h3>
          <AlertForm
            onSubmit={handleCreateAlert}
            onCancel={() => setViewMode('list')}
            initialSymbol={filterSymbol}
            initialExchange={filterExchange}
          />
        </div>
      )}

      {viewMode === 'list' && (
        <>
          {/* Filters */}
          <div className="grid grid-cols-3 gap-2 mb-4">
            <input
              type="text"
              placeholder="Filter by symbol..."
              value={filterSymbol}
              onChange={e => setFilterSymbol(e.target.value)}
              className="px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white placeholder-zinc-500"
            />
            <input
              type="text"
              placeholder="Filter by exchange..."
              value={filterExchange}
              onChange={e => setFilterExchange(e.target.value)}
              className="px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white placeholder-zinc-500"
            />
            <label className="flex items-center gap-2 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white">
              <input
                type="checkbox"
                checked={enabledOnly}
                onChange={e => setEnabledOnly(e.target.checked)}
                className="rounded"
              />
              <span className="text-xs">Enabled only</span>
            </label>
          </div>

          {/* Alert List */}
          {isLoading && <div className="text-center text-zinc-400 py-8">Loading alerts...</div>}

          {error && (
            <div className="text-center text-red-400 py-8">
              Failed to load alerts. Please try again.
            </div>
          )}

          {!isLoading && !error && alertsData && alertsData.alerts.length === 0 && (
            <div className="text-center text-zinc-500 py-8">
              No alerts found. Create your first alert to get started!
            </div>
          )}

          {!isLoading && !error && alertsData && alertsData.alerts.length > 0 && (
            <div className="space-y-2">
              {alertsData.alerts.map(alert => (
                <div
                  key={alert.id}
                  className={`p-3 rounded-lg border ${
                    alert.enabled
                      ? 'bg-zinc-800 border-zinc-700'
                      : 'bg-zinc-900 border-zinc-800 opacity-50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-lg">{getAlertIcon(alert.condition_type)}</span>
                        <span className="font-bold text-white text-sm">
                          {alert.symbol} / {alert.exchange}
                        </span>
                        <span className="text-xs text-zinc-500">{alert.timeframe}</span>
                        {!alert.enabled && (
                          <span className="px-1.5 py-0.5 bg-zinc-700 text-zinc-400 rounded text-xs">
                            Disabled
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-zinc-400">
                        {getAlertTypeLabel(alert.condition_type)} {alert.operator}{' '}
                        {alert.threshold_value}
                        {alert.indicator_params &&
                          ` (period: ${alert.indicator_params.period || 'default'})`}
                      </div>
                      {alert.triggered_at && (
                        <div className="text-xs text-zinc-500 mt-1">
                          Last triggered: {new Date(alert.triggered_at).toLocaleString()} (
                          {alert.trigger_count}x)
                        </div>
                      )}
                    </div>

                    <div className="flex gap-1">
                      <button
                        onClick={() => handleToggleAlert(alert)}
                        className={`px-2 py-1 rounded text-xs ${
                          alert.enabled
                            ? 'bg-zinc-700 hover:bg-zinc-600 text-white'
                            : 'bg-green-700 hover:bg-green-600 text-white'
                        }`}
                      >
                        {alert.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        onClick={() => handleDeleteAlert(alert.id)}
                        className="px-2 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-xs"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!isLoading && !error && alertsData && (
            <div className="mt-4 text-xs text-zinc-500 text-center">
              {alertsData.count} alert{alertsData.count !== 1 ? 's' : ''} total
            </div>
          )}
        </>
      )}
    </div>
  )
}
