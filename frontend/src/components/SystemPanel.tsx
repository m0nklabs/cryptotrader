import React from 'react';
import { AlertCircle, CheckCircle, AlertTriangle } from 'lucide-react';
import { useHealthCheck } from '../hooks/useHealthCheck';

interface ComponentStatus {
  status: 'ok' | 'degraded' | 'error';
  message?: string;
  latency_ms?: number;
  uptime_seconds?: number;
  details?: Record<string, any>;
}

interface HealthData {
  overall: {
    status: 'ok' | 'degraded' | 'error';
  };
  api?: ComponentStatus;
  database?: ComponentStatus;
  ingestion?: ComponentStatus;
}

export function SystemPanel() {
  const { data: health, isLoading, error } = useHealthCheck();

  if (isLoading) {
    return (
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">System Health</h3>
        <p className="text-xs text-gray-500">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">System Health</h3>
        <div className="flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-500" />
          <span className="text-xs text-red-500">Unable to fetch health status</span>
        </div>
      </div>
    );
  }

  const healthData = health as HealthData;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'ok':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'degraded':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      default:
        return <AlertCircle className="w-4 h-4 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ok':
        return 'text-green-500';
      case 'degraded':
        return 'text-yellow-500';
      case 'error':
        return 'text-red-500';
      default:
        return 'text-gray-500';
    }
  };

  const formatUptime = (seconds?: number): string => {
    if (!seconds) return 'N/A';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
      <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
        System Health
        {getStatusIcon(healthData.overall.status)}
      </h3>

      <div className="space-y-2">
        {/* API Status */}
        {healthData.api && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400">API</span>
            <div className="flex items-center gap-2">
              {healthData.api.uptime_seconds !== undefined && (
                <span className="text-gray-500">{formatUptime(healthData.api.uptime_seconds)}</span>
              )}
              {getStatusIcon(healthData.api.status)}
              <span className={getStatusColor(healthData.api.status)}>{healthData.api.status}</span>
            </div>
          </div>
        )}

        {/* Database Status */}
        {healthData.database && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400">Database</span>
            <div className="flex items-center gap-2">
              {healthData.database.latency_ms !== undefined && (
                <span className="text-gray-500">{healthData.database.latency_ms.toFixed(1)}ms</span>
              )}
              {getStatusIcon(healthData.database.status)}
              <span className={getStatusColor(healthData.database.status)}>{healthData.database.status}</span>
            </div>
          </div>
        )}

        {/* Ingestion Status */}
        {healthData.ingestion && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400">Ingestion</span>
            <div className="flex items-center gap-2">
              {getStatusIcon(healthData.ingestion.status)}
              <span className={getStatusColor(healthData.ingestion.status)}>{healthData.ingestion.status}</span>
            </div>
          </div>
        )}
      </div>

      {/* Additional details */}
      {healthData.database?.details && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <p className="text-xs text-gray-500">
            Candles: {healthData.database.details.candle_count?.toLocaleString() || 'N/A'}
          </p>
        </div>
      )}
    </div>
  );
}
