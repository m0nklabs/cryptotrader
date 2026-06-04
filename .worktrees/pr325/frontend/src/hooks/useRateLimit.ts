import { useQuery } from '@tanstack/react-query';

export function useRateLimit(exchange?: string) {
  return useQuery({
    queryKey: ['rateLimit', exchange],
    queryFn: async () => {
      const url = exchange
        ? `/ratelimit/status?exchange=${exchange}`
        : `/ratelimit/status`;

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
