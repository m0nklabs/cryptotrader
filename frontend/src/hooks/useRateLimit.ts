import { useQuery } from '@tanstack/react-query';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function useRateLimit(exchange?: string) {
  return useQuery({
    queryKey: ['rateLimit', exchange],
    queryFn: async () => {
      const url = exchange
        ? `${API_BASE_URL}/ratelimit/status?exchange=${exchange}`
        : `${API_BASE_URL}/ratelimit/status`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Failed to fetch rate limits');
      }
      return response.json();
    },
    refetchInterval: 10000, // Refresh every 10 seconds
    retry: 2,
  });
}
