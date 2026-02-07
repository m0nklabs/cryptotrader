import { useQuery } from '@tanstack/react-query';

export function useHealthCheck() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const response = await fetch('/system/health');
      if (!response.ok) {
        throw new Error('Health check failed');
      }
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}
