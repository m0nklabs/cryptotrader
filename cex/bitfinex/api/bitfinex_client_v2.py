"""
Bitfinex API v2 Client - REST API Implementation
=================================================

Pure REST API client using requests library only.
Provides backwards-compatible interface without external dependencies.

Features:
- Public API (tickers, orderbook, trades, candles)
- Authenticated API (wallets, orders, trades)
- Built on requests library only (no bfxapi dependency)

Usage:
    from bitfinex_client_v2 import BitfinexClient
    
    client = BitfinexClient(api_key="...", api_secret="...")
    wallets = client.get_wallets()
    ticker = client.get_ticker("tBTCUSD")
"""

import os
from typing import Any, Dict, List, Optional

import requests


class BitfinexClient:
    """
    Bitfinex API v2 REST Client
    
    Pure REST API implementation using requests library.
    Provides simple interface for both public and authenticated endpoints.
    """
    
    BASE_URL = "https://api-pub.bitfinex.com/v2"
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize Bitfinex client.
        
        Args:
            api_key: API key for authenticated endpoints (optional for public API)
            api_secret: API secret for authenticated endpoints (optional for public API)
        """
        self.api_key = (
            api_key
            or os.getenv('BITFINEX_API_KEY')
            or os.getenv('BITFINEX_API_KEY_SUB')
            or os.getenv('BITFINEX_API_KEY_MAIN')
            or os.getenv('BITFINEX_API_KEY_TEST')
        )
        self.api_secret = (
            api_secret
            or os.getenv('BITFINEX_API_SECRET')
            or os.getenv('BITFINEX_API_SECRET_SUB')
            or os.getenv('BITFINEX_API_SECRET_MAIN')
            or os.getenv('BITFINEX_API_SECRET_TEST')
        )
    
    # ==================== Public API Methods ====================
    
    def get_trading_pairs(self) -> List[str]:
        """
        Get all available trading pairs on Bitfinex.
        
        Returns:
            List of trading pair symbols (e.g., ['BTCUSD', 'ETHUSD', 'LTCBTC', ...])
        
        Example:
            >>> client = BitfinexClient()
            >>> pairs = client.get_trading_pairs()
            >>> print(f"Found {len(pairs)} trading pairs")
            Found 400+ trading pairs
        """
        try:
            # Public API endpoint - no auth needed
            response = requests.get(
                'https://api-pub.bitfinex.com/v2/conf/pub:list:pair:exchange',
                timeout=10
            )
            response.raise_for_status()
            
            # Response format: [[pairs...]]
            data = response.json()
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                return data[0]
            
            return []
            
        except Exception as e:
            print(f"Error fetching Bitfinex trading pairs: {e}")
            return []
    
    def extract_unique_coins(self, trading_pairs: List[str]) -> List[str]:
        """
        Extract unique base coins from trading pair symbols.
        
        Args:
            trading_pairs: List of trading symbols (e.g., ['BTCUSD', 'ETHUSD', 'BTC:USD'])
        
        Returns:
            Sorted list of unique coin symbols (e.g., ['BTC', 'ETH', 'LTC', 'USD', ...])
        
        Example:
            >>> pairs = ['BTCUSD', 'ETHUSD', 'LTCBTC', 'XMR:USD']
            >>> coins = client.extract_unique_coins(pairs)
            >>> print(coins)
            ['BTC', 'ETH', 'LTC', 'USD', 'XMR']
        """
        coins = set()
        
        for pair in trading_pairs:
            # Handle both formats: "BTCUSD" and "BTC:USD"
            if ':' in pair:
                parts = pair.split(':')
                coins.update(parts)
            else:
                # Try to split by known quote currencies
                quote_currencies = ['USD', 'USDT', 'EUR', 'GBP', 'JPY', 'BTC', 'ETH', 'UST']
                
                for quote in quote_currencies:
                    if pair.endswith(quote):
                        base = pair[:-len(quote)]
                        if base and base != quote:  # Ensure base is not empty or same as quote
                            coins.add(base)
                            coins.add(quote)
                        break
        
        return sorted(list(coins))
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get ticker for a trading pair.
        
        Args:
            symbol: Trading pair symbol (e.g., 'tBTCUSD')
        
        Returns:
            Dict with ticker data (bid, ask, last_price, volume, etc.)
            
        Example:
            >>> client = BitfinexClient()
            >>> ticker = client.get_ticker('tBTCUSD')
            >>> print(f"BTC/USD: ${ticker['last_price']:.2f}")
        """
        try:
            # Ensure symbol starts with 't'
            if not symbol.startswith('t'):
                symbol = 't' + symbol
            
            response = requests.get(
                f'{self.BASE_URL}/ticker/{symbol}',
                timeout=10
            )
            response.raise_for_status()
            
            # Response format: [BID, BID_SIZE, ASK, ASK_SIZE, DAILY_CHANGE, DAILY_CHANGE_RELATIVE, LAST_PRICE, VOLUME, HIGH, LOW]
            data = response.json()
            
            return {
                'symbol': symbol,
                'bid': float(data[0]),
                'bid_size': float(data[1]),
                'ask': float(data[2]),
                'ask_size': float(data[3]),
                'daily_change': float(data[4]),
                'daily_change_relative': float(data[5]),
                'last_price': float(data[6]),
                'volume': float(data[7]),
                'high': float(data[8]),
                'low': float(data[9])
            }
            
        except Exception as e:
            print(f"Error fetching ticker for {symbol}: {e}")
            # Return empty dict with symbol
            return {
                'symbol': symbol,
                'bid': 0.0,
                'ask': 0.0,
                'last_price': 0.0,
                'error': str(e)
            }
    
    def get_tickers(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Get tickers for multiple trading pairs.
        
        Args:
            symbols: List of trading pair symbols (e.g., ['tBTCUSD', 'tETHUSD'])
        
        Returns:
            List of ticker dicts
        """
        tickers = self.client.rest.public.get_t_tickers(symbols)
        # get_t_tickers returns a dict with symbols as keys
        return [
            {
                'symbol': symbol,
                'bid': ticker.bid,
                'ask': ticker.ask,
                'last_price': ticker.last_price,
                'volume': ticker.volume,
                'daily_change': ticker.daily_change,
                'daily_change_relative': ticker.daily_change_relative
            }
            for symbol, ticker in tickers.items()
        ]
    
    def get_orderbook(self, symbol: str, precision: str = 'P0', length: int = 25) -> Dict[str, Any]:
        """
        Get orderbook for a trading pair.
        
        Args:
            symbol: Trading pair symbol (e.g., 'tBTCUSD')
            precision: Price aggregation level (P0, P1, P2, P3, P4)
            length: Number of price points (1, 25, or 100)
        
        Returns:
            Dict with bids and asks
        """
        # Map length to allowed values
        if length <= 1:
            len_param = 1
        elif length <= 25:
            len_param = 25
        else:
            len_param = 100
        
        book = self.client.rest.public.get_t_book(symbol, precision, len=len_param)
        
        bids = []
        asks = []
        
        for entry in book:
            price = entry.price
            count = entry.count
            amount = entry.amount
            
            if amount > 0:
                bids.append({'price': price, 'count': count, 'amount': amount})
            else:
                asks.append({'price': price, 'count': count, 'amount': abs(amount)})
        
        return {
            'symbol': symbol,
            'bids': sorted(bids, key=lambda x: x['price'], reverse=True),
            'asks': sorted(asks, key=lambda x: x['price'])
        }
    
    def get_trades(self, symbol: str, limit: int = 120, start: Optional[int] = None,
                   end: Optional[int] = None, sort: int = -1) -> List[Dict[str, Any]]:
        """
        Get recent trades for a trading pair.
        
        Args:
            symbol: Trading pair symbol (e.g., 'tBTCUSD')
            limit: Number of trades to return (default: 120, max: 10000)
            start: Start timestamp in milliseconds
            end: End timestamp in milliseconds
            sort: Sort direction (1 = oldest first, -1 = newest first)
        
        Returns:
            List of trade dicts
        """
        # Build kwargs for optional parameters
        kwargs = {}
        if limit is not None:
            kwargs['limit'] = limit
        if start is not None:
            kwargs['start'] = str(start)
        if end is not None:
            kwargs['end'] = str(end)
        if sort is not None:
            kwargs['sort'] = sort
        
        trades = self.client.rest.public.get_t_trades(symbol, **kwargs)
        return [
            {
                'id': t.id,
                'timestamp': t.mts,
                'amount': t.amount,
                'price': t.price
            }
            for t in trades
        ]
    
    def get_candles(self, timeframe: str, symbol: str, section: str = 'hist',
                    limit: Optional[int] = None, start: Optional[int] = None,
                    end: Optional[int] = None, sort: int = -1) -> List[Dict[str, Any]]:
        """
        Get candlestick data (OHLCV).
        
        Args:
            timeframe: Candle timeframe (1m, 5m, 15m, 30m, 1h, 3h, 6h, 12h, 1D, 7D, 14D, 1M)
            symbol: Trading pair symbol (e.g., 'tBTCUSD')
            section: 'hist' for historical or 'last' for last candle
            limit: Number of candles to return
            start: Start timestamp in milliseconds
            end: End timestamp in milliseconds
            sort: Sort direction (1 = oldest first, -1 = newest first)
        
        Returns:
            List of candle dicts with OHLCV data
        """
        candles = self.client.rest.public.get_t_candles(timeframe, symbol, section, limit, start, end, sort)
        return [
            {
                'timestamp': c.mts,
                'open': c.open,
                'close': c.close,
                'high': c.high,
                'low': c.low,
                'volume': c.volume
            }
            for c in candles
        ]
    
    # ==================== Authenticated API Methods ====================
    
    def get_wallets(self) -> List[Dict[str, Any]]:
        """
        Get all wallet balances (requires authentication).
        
        Returns:
            List of wallet dicts with balance info
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for authenticated endpoints")
        
        wallets = self.client.rest.auth.get_wallets()
        return [
            {
                'type': w.wallet_type,
                'currency': w.currency,
                'balance': w.balance,
                'unsettled_interest': w.unsettled_interest,
                'available_balance': w.available_balance
            }
            for w in wallets
        ]
    
    def get_active_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all active orders (requires authentication).
        
        Args:
            symbol: Optional trading pair symbol to filter by
        
        Returns:
            List of active order dicts
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for authenticated endpoints")
        
        # get_orders returns all active orders
        orders = self.client.rest.auth.get_orders(symbol) if symbol else self.client.rest.auth.get_orders()
        return [
            {
                'id': o.id,
                'symbol': o.symbol,
                'amount': o.amount,
                'amount_orig': o.amount_orig,
                'type': o.order_type,
                'status': o.order_status,
                'price': o.price,
                'created_at': o.mts_create,
                'updated_at': o.mts_update
            }
            for o in orders
        ]
    
    def submit_order(self, symbol: str, amount: float, price: float = None,
                    order_type: str = 'EXCHANGE LIMIT', flags: int = 0,
                    cid: Optional[int] = None) -> Dict[str, Any]:
        """
        Submit a new order (requires authentication).
        
        Args:
            symbol: Trading pair symbol (e.g., 'tBTCUSD')
            amount: Order amount (positive for buy, negative for sell)
            price: Order price (required for LIMIT orders)
            order_type: Order type (EXCHANGE LIMIT, EXCHANGE MARKET, etc.)
            flags: Order flags (bitfield)
            cid: Client order ID (optional)
        
        Returns:
            Dict with order confirmation
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for authenticated endpoints")
        
        result = self.client.rest.auth.submit_order(
            symbol=symbol,
            amount=amount,
            price=price,
            market_type=order_type,
            flags=flags,
            cid=cid
        )
        
        return {
            'status': 'success',
            'order_id': result[0][0][0] if result and len(result[0]) > 0 else None,
            'data': result
        }
    
    def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """
        Cancel an active order (requires authentication).
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            Dict with cancellation confirmation
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for authenticated endpoints")
        
        result = self.client.rest.auth.cancel_order(order_id)
        return {
            'status': 'success',
            'order_id': order_id,
            'data': result
        }
    
    def get_order_trades(self, symbol: str, order_id: int) -> List[Dict[str, Any]]:
        """
        Get trades for a specific order (requires authentication).
        
        Args:
            symbol: Trading pair symbol
            order_id: Order ID
        
        Returns:
            List of trade dicts for this order
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for authenticated endpoints")
        
        trades = self.client.rest.auth.get_order_trades(symbol, order_id)
        return [
            {
                'id': t.id,
                'symbol': t.symbol,
                'mts_create': t.mts_create,
                'order_id': t.order_id,
                'exec_amount': t.exec_amount,
                'exec_price': t.exec_price,
                'fee': t.fee,
                'fee_currency': t.fee_currency
            }
            for t in trades
        ]
    
    def transfer_between_wallets(self, from_wallet: str, to_wallet: str, 
                                 currency: str, amount: float) -> Dict[str, Any]:
        """
        Transfer funds between wallet types within the same account (requires authentication).
        
        Args:
            from_wallet: Source wallet type ('exchange', 'margin', 'funding')
            to_wallet: Destination wallet type ('exchange', 'margin', 'funding')
            currency: Currency code (e.g., 'BTC', 'USD')
            amount: Amount to transfer
        
        Returns:
            Dict with transfer confirmation
        
        Example:
            # Transfer 0.01 BTC from exchange to margin wallet
            result = client.transfer_between_wallets('exchange', 'margin', 'BTC', 0.01)
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for authenticated endpoints")
        
        result = self.client.rest.auth.transfer_between_wallets(
            from_wallet=from_wallet,
            to_wallet=to_wallet,
            currency=currency,
            currency_to=currency,
            amount=amount
        )
        
        return {
            'status': 'success',
            'from_wallet': from_wallet,
            'to_wallet': to_wallet,
            'currency': currency,
            'amount': amount,
            'data': result
        }
    
    def get_orders_history(self, symbol: Optional[str] = None, start: Optional[int] = None,
                          end: Optional[int] = None, limit: int = 25) -> List[Dict[str, Any]]:
        """
        Get order history (requires authentication).
        
        Args:
            symbol: Optional trading pair symbol to filter by
            start: Start timestamp in milliseconds
            end: End timestamp in milliseconds
            limit: Number of orders to return (default: 25, max: 2500)
        
        Returns:
            List of historical order dicts
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for authenticated endpoints")
        
        # Build kwargs for optional parameters
        kwargs = {}
        if symbol:
            kwargs['symbol'] = symbol
        if start:
            kwargs['start'] = str(start)
        if end:
            kwargs['end'] = str(end)
        if limit:
            kwargs['limit'] = limit
        
        orders = self.client.rest.auth.get_orders_history(**kwargs)
        return [
            {
                'id': o.id,
                'symbol': o.symbol,
                'amount': o.amount,
                'amount_orig': o.amount_orig,
                'type': o.order_type,
                'status': o.order_status,
                'price': o.price,
                'created_at': o.mts_create,
                'updated_at': o.mts_update
            }
            for o in orders
        ]
    
    def get_deposit_address(self, wallet: str, method: str, op_renew: int = 0) -> Dict[str, Any]:
        """
        Get deposit address for a currency (requires authentication).
        
        Args:
            wallet: Wallet type ('exchange', 'margin', 'funding')
            method: Deposit method/currency (e.g., 'bitcoin', 'litecoin', 'ethereum')
            op_renew: Whether to generate new address (0 = use existing, 1 = generate new)
        
        Returns:
            Dict with deposit address info including address, method, currency
        
        Example:
            # Get LTC deposit address
            result = client.get_deposit_address('exchange', 'litecoin')
            print(result['address'])
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for authenticated endpoints")
        
        result = self.client.rest.auth.get_deposit_address(
            wallet=wallet,
            method=method,
            op_renew=op_renew
        )
        
        # Result format varies, handle both object and tuple formats
        if hasattr(result, '__dict__'):
            return {
                'method': getattr(result, 'method', method),
                'currency': getattr(result, 'currency', method),
                'address': getattr(result, 'address', None),
                'pool_address': getattr(result, 'pool_address', None)
            }
        else:
            # Tuple format: [wallet, method, address, pool_address, ...]
            return {
                'wallet': result[0] if len(result) > 0 else wallet,
                'method': result[1] if len(result) > 1 else method,
                'address': result[2] if len(result) > 2 else None,
                'pool_address': result[3] if len(result) > 3 else None
            }


# Convenience function for quick initialization
def create_client(api_key: Optional[str] = None, api_secret: Optional[str] = None) -> BitfinexClient:
    """
    Create a BitfinexClient instance.
    
    Args:
        api_key: API key (optional, will use BITFINEX_API_KEY env var if not provided)
        api_secret: API secret (optional, will use BITFINEX_API_SECRET env var if not provided)
    
    Returns:
        BitfinexClient instance
    """
    return BitfinexClient(api_key=api_key, api_secret=api_secret)
