/**
 * Real-time candle streaming client using Server-Sent Events (SSE).
 * Provides live candle updates with automatic reconnection.
 */

export type CandleUpdate = {
  type: 'candle';
  symbol: string;
  timeframe: string;
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
};

export type HeartbeatMessage = {
  type: 'heartbeat';
  timestamp: number;
};

export type StreamMessage = CandleUpdate | HeartbeatMessage;

export type CandleStreamCallback = (candle: CandleUpdate) => void;

/**
 * CandleStream manages a Server-Sent Events connection for real-time candle updates.
 */
export class CandleStream {
  private eventSource: EventSource | null = null;
  private symbol: string;
  private timeframe: string;
  private callback: CandleStreamCallback;
  private onError?: (error: Event) => void;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second

  constructor(
    symbol: string,
    timeframe: string,
    callback: CandleStreamCallback,
    onError?: (error: Event) => void
  ) {
    this.symbol = symbol;
    this.timeframe = timeframe;
    this.callback = callback;
    this.onError = onError;
  }

  /**
   * Connect to the SSE stream.
   */
  connect(): void {
    if (this.eventSource) {
      this.eventSource.close();
    }

    const url = `/candles/stream?symbol=${encodeURIComponent(this.symbol)}&timeframe=${encodeURIComponent(
      this.timeframe
    )}`;

    console.log(`[CandleStream] Connecting to ${url}`);

    this.eventSource = new EventSource(url);

    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as StreamMessage;

        if (data.type === 'candle') {
          this.callback(data);
          this.reconnectAttempts = 0; // Reset on successful message
          this.reconnectDelay = 1000;
        } else if (data.type === 'heartbeat') {
          // Heartbeat received, connection is alive
          console.debug('[CandleStream] Heartbeat received');
        }
      } catch (err) {
        console.error('[CandleStream] Failed to parse message:', err);
      }
    };

    this.eventSource.onerror = (error) => {
      console.error('[CandleStream] Connection error:', error);

      // Close the connection
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      // Notify error handler
      if (this.onError) {
        this.onError(error);
      }

      // Attempt reconnection with exponential backoff
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        console.log(`[CandleStream] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => {
          this.connect();
        }, delay);
      } else {
        console.error('[CandleStream] Max reconnection attempts reached, giving up');
      }
    };

    this.eventSource.onopen = () => {
      console.log(`[CandleStream] Connected to ${url}`);
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1000;
    };
  }

  /**
   * Disconnect from the SSE stream.
   */
  disconnect(): void {
    if (this.eventSource) {
      console.log('[CandleStream] Disconnecting');
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  /**
   * Check if currently connected.
   */
  isConnected(): boolean {
    return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN;
  }
}

/**
 * Create and connect to a candle stream.
 */
export function createCandleStream(
  symbol: string,
  timeframe: string,
  callback: CandleStreamCallback,
  onError?: (error: Event) => void
): CandleStream {
  const stream = new CandleStream(symbol, timeframe, callback, onError);
  stream.connect();
  return stream;
}
