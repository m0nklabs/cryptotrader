import React from 'react';
import { RefreshCw } from 'lucide-react';
import { useRateLimit } from '../hooks/useRateLimit';
import { RateLimitBar } from './RateLimitBar';

export function RateLimitPanel() {
  const { data, isLoading, error, refetch } = useRateLimit();

  if (isLoading) {
    return (
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Rate Limits</h3>
        <p className="text-xs text-gray-500">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Rate Limits</h3>
        <p className="text-xs text-red-500">Error loading rate limits</p>
      </div>
    );
  }

  const limits = data?.limits || [];
  const hasLimits = limits.length > 0;

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-300">Rate Limits</h3>
        <button
          onClick={() => refetch()}
          className="text-gray-400 hover:text-gray-300 transition-colors"
          title="Refresh rate limits"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {!hasLimits && (
        <p className="text-xs text-gray-500">
          No rate limit data available. Rate limits are tracked automatically when making API requests.
        </p>
      )}

      {hasLimits && (
        <div className="space-y-2">
          {limits.map((limit: any) => (
            <RateLimitBar
              key={`${limit.exchange}:${limit.endpoint}`}
              exchange={limit.exchange}
              endpoint={limit.endpoint}
              used={limit.used}
              limit={limit.limit}
              usagePercent={limit.usage_percent}
              resetInSeconds={limit.reset_in_seconds}
              status={limit.status}
            />
          ))}
        </div>
      )}

      {/* Summary */}
      {hasLimits && (
        <div className="mt-3 pt-3 border-t border-gray-800 text-xs text-gray-500">
          {data.count} endpoint{data.count !== 1 ? 's' : ''} tracked
        </div>
      )}
    </div>
  );
}
