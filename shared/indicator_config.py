#!/usr/bin/env python3
"""
Indicator Configuration Manager

Manages indicator metadata, weights, and signals from database.
Provides centralized configuration for all trading indicators.
"""

import logging
import os
from typing import Dict, List, Optional
from sqlalchemy import text
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)


_engine = None


def _get_engine():
    """Return a SQLAlchemy engine if DATABASE_URL is configured, else None."""
    global _engine
    if _engine is not None:
        return _engine
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    _engine = create_engine(database_url, echo=False)
    return _engine


class IndicatorConfig:
    """Manages indicator configuration from database"""
    
    def __init__(self, user_id: int = 1, strategy: str = 'default'):
        """
        Initialize indicator configuration
        
        Args:
            user_id: User ID for personalized weights
            strategy: Strategy name (default, aggressive, conservative, etc.)
        """
        self.user_id = user_id
        self.strategy = strategy
        self._cache = {}
        self._load_config()
    
    def _load_config(self):
        """Load indicator configuration from database"""
        try:
            engine = _get_engine()
            if engine is None:
                raise RuntimeError("DATABASE_URL not set")
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        i.id,
                        i.code,
                        i.name,
                        i.category,
                        i.indicator_type,
                        i.description,
                        COALESCE(iw.weight, i.default_weight) as weight,
                        i.is_active
                    FROM indicators i
                    LEFT JOIN indicator_weights iw 
                        ON i.id = iw.indicator_id 
                        AND iw.user_id = :user_id 
                        AND iw.strategy = :strategy
                    WHERE i.is_active = true
                    ORDER BY i.category, weight DESC
                """), {'user_id': self.user_id, 'strategy': self.strategy})
                
                for row in result:
                    self._cache[row.code] = {
                        'id': row.id,
                        'code': row.code,
                        'name': row.name,
                        'category': row.category,
                        'indicator_type': row.indicator_type,
                        'description': row.description,
                        'weight': float(row.weight),
                        'is_active': row.is_active
                    }
                
                logger.info(f"📊 Loaded {len(self._cache)} indicator configurations for user {self.user_id}, strategy '{self.strategy}'")
                
        except Exception as e:
            logger.error(f"❌ Failed to load indicator config: {e}")
            self._use_defaults()
    
    def _use_defaults(self):
        """Fallback to hardcoded defaults if database fails"""
        logger.warning("⚠️  Using hardcoded default weights (database unavailable)")
        self._cache = {
            'RSI': {'weight': 0.15, 'category': 'momentum'},
            'MACD': {'weight': 0.20, 'category': 'momentum'},
            'STOCHASTIC': {'weight': 0.15, 'category': 'momentum'},
            'BOLLINGER': {'weight': 0.15, 'category': 'volatility'},
            'ATR': {'weight': 0.10, 'category': 'volatility'},
            'VOLUME': {'weight': 0.10, 'category': 'volume'},
            'OBV': {'weight': 0.10, 'category': 'volume'},
            'PEAK_HILO': {'weight': 0.20, 'category': 'trend'},
            'MA_CROSS': {'weight': 0.15, 'category': 'trend'}
        }
    
    def get_weight(self, code: str) -> float:
        """
        Get weight for specific indicator
        
        Args:
            code: Indicator code (RSI, MACD, PEAK_HILO, etc.)
        
        Returns:
            Weight value (0.0-1.0)
        """
        if code in self._cache:
            return self._cache[code].get('weight', 0.15)
        
        logger.warning(f"⚠️  Unknown indicator '{code}', using default weight 0.15")
        return 0.15
    
    def get_all_weights(self) -> Dict[str, float]:
        """
        Get all indicator weights
        
        Returns:
            Dictionary mapping indicator codes to weights
        """
        return {code: cfg['weight'] for code, cfg in self._cache.items()}
    
    def get_indicators_by_category(self, category: str) -> List[Dict]:
        """
        Get all indicators in a category
        
        Args:
            category: Category name (momentum, trend, volatility, volume)
        
        Returns:
            List of indicator configs
        """
        return [cfg for cfg in self._cache.values() if cfg.get('category') == category]
    
    def update_weight(self, code: str, weight: float) -> bool:
        """
        Update weight for indicator
        
        Args:
            code: Indicator code
            weight: New weight value
        
        Returns:
            True if successful
        """
        try:
            if code not in self._cache:
                logger.error(f"❌ Unknown indicator '{code}'")
                return False

            engine = _get_engine()
            if engine is None:
                raise RuntimeError("DATABASE_URL not set")
            
            indicator_id = self._cache[code]['id']
            
            with engine.connect() as conn:
                # Insert or update weight
                conn.execute(text("""
                    INSERT INTO indicator_weights (indicator_id, user_id, weight, strategy)
                    VALUES (:indicator_id, :user_id, :weight, :strategy)
                    ON CONFLICT (indicator_id, user_id, strategy)
                    DO UPDATE SET weight = :weight, updated_at = CURRENT_TIMESTAMP
                """), {
                    'indicator_id': indicator_id,
                    'user_id': self.user_id,
                    'weight': weight,
                    'strategy': self.strategy
                })
                
                conn.commit()
            
            # Update cache
            self._cache[code]['weight'] = weight
            logger.info(f"✅ Updated {code} weight to {weight}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update weight: {e}")
            return False
    
    def log_signal(self, code: str, coin_id: int, timeframe: str, 
                   signal: str, strength: int, value: Optional[float] = None,
                   reason: Optional[str] = None):
        """
        Log indicator signal to database for backtesting
        
        Args:
            code: Indicator code
            coin_id: Coin ID
            timeframe: Timeframe (1h, 4h, 1d, etc.)
            signal: Signal type (BUY, SELL, HOLD)
            strength: Signal strength (0-100)
            value: Indicator value
            reason: Human-readable reason
        """
        try:
            if code not in self._cache:
                logger.warning(f"⚠️  Cannot log signal for unknown indicator '{code}'")
                return

            engine = _get_engine()
            if engine is None:
                raise RuntimeError("DATABASE_URL not set")
            
            indicator_id = self._cache[code]['id']
            
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO indicator_signals 
                    (indicator_id, coin_id, timeframe, signal, strength, value, reason)
                    VALUES (:indicator_id, :coin_id, :timeframe, :signal, :strength, :value, :reason)
                """), {
                    'indicator_id': indicator_id,
                    'coin_id': coin_id,
                    'timeframe': timeframe,
                    'signal': signal,
                    'strength': strength,
                    'value': value,
                    'reason': reason
                })
                
                conn.commit()
            
        except Exception as e:
            logger.warning(f"⚠️  Failed to log signal: {e}")
    
    def get_total_weight(self) -> float:
        """Get sum of all active indicator weights"""
        return sum(cfg['weight'] for cfg in self._cache.values())
    
    def normalize_weights(self) -> Dict[str, float]:
        """
        Get normalized weights (sum to 1.0)
        
        Returns:
            Dictionary of normalized weights
        """
        total = self.get_total_weight()
        if total == 0:
            return {}
        
        return {code: cfg['weight'] / total for code, cfg in self._cache.items()}
    
    def __repr__(self):
        return f"<IndicatorConfig user={self.user_id} strategy='{self.strategy}' indicators={len(self._cache)}>"


# Global instance (singleton pattern)
_config_instance = None

def get_indicator_config(user_id: int = 1, strategy: str = 'default') -> IndicatorConfig:
    """
    Get indicator configuration instance (cached)
    
    Args:
        user_id: User ID
        strategy: Strategy name
    
    Returns:
        IndicatorConfig instance
    """
    global _config_instance
    
    if _config_instance is None or _config_instance.user_id != user_id or _config_instance.strategy != strategy:
        _config_instance = IndicatorConfig(user_id, strategy)
    
    return _config_instance


if __name__ == '__main__':
    # Test indicator config
    logging.basicConfig(level=logging.INFO)
    
    config = get_indicator_config()
    
    print("\n" + "="*80)
    print("📊 INDICATOR CONFIGURATION TEST")
    print("="*80)
    
    print(f"\n{config}")
    print(f"Total weight: {config.get_total_weight():.2f}")
    
    print("\n🏷️  All Weights:")
    for code, weight in config.get_all_weights().items():
        print(f"  {code:15} → {weight:.2f}")
    
    print("\n📈 Normalized Weights (sum to 1.0):")
    for code, weight in config.normalize_weights().items():
        print(f"  {code:15} → {weight:.4f}")
    
    print("\n🎯 Trend Indicators:")
    for ind in config.get_indicators_by_category('trend'):
        print(f"  {ind['code']:15} | {ind['name']:35} | {ind['weight']:.2f}")
    
    print("\n" + "="*80)
