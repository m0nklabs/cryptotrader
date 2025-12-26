/**
 * System status API client.
 * Connects to backend health check endpoints.
 */

export interface SystemStatus {
  backend: {
    status: 'ok' | 'error';
    uptime_seconds: number;
  };
  database: {
    status: 'ok' | 'error';
    connected: boolean;
    latency_ms: number | null;
    error?: string;
  };
  timestamp: number;
}

/**
 * Fetch comprehensive system health status.
 */
export async function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  const response = await fetch('/api/system/status', { signal });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const data = await response.json();
  return data as SystemStatus;
}
