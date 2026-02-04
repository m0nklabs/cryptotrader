import React from 'react';
import { AlertTriangle, CheckCircle, Clock } from 'lucide-react';

interface RateLimitBarProps {
  exchange: string;
  endpoint: string;
  used: number;
  limit: number;
  usagePercent: number;
  resetInSeconds: number;
  status: 'ok' | 'warning' | 'critical';
}

export function RateLimitBar({
  exchange,
  endpoint,
  used,
  limit,
  usagePercent,
  resetInSeconds,
  status,
}: RateLimitBarProps) {
  const getBarColor = () => {
    switch (status) {
      case 'ok':
        return 'bg-green-500';
      case 'warning':
        return 'bg-yellow-500';
      case 'critical':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getTextColor = () => {
    switch (status) {
      case 'ok':
        return 'text-green-500';
      case 'warning':
        return 'text-yellow-500';
      case 'critical':
        return 'text-red-500';
      default:
        return 'text-gray-500';
    }
  };

  const formatResetTime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s`;
    }
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m`;
  };

  return (
    <div className="bg-gray-800 rounded p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-300">
            {exchange}
          </span>
          <span className="text-xs text-gray-500">/</span>
          <span className="text-xs text-gray-400">{endpoint}</span>
        </div>
        {status === 'critical' && (
          <AlertTriangle className="w-4 h-4 text-red-500" />
        )}
        {status === 'ok' && (
          <CheckCircle className="w-4 h-4 text-green-500" />
        )}
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-700 rounded-full h-2">
        <div
          className={`${getBarColor()} h-2 rounded-full transition-all duration-300`}
          style={{ width: `${Math.min(usagePercent, 100)}%` }}
        />
      </div>

      {/* Stats */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className={getTextColor()}>
            {used} / {limit}
          </span>
          <span className="text-gray-500">
            ({usagePercent.toFixed(1)}%)
          </span>
        </div>
        <div className="flex items-center gap-1 text-gray-500">
          <Clock className="w-3 h-3" />
          <span>resets in {formatResetTime(resetInSeconds)}</span>
        </div>
      </div>
    </div>
  );
}
