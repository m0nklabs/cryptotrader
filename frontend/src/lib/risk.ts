/**
 * Risk calculation utilities for position sizing and risk management.
 */

export interface PositionSizeResult {
  positionSize: number;
  riskAmount: number;
  stopLossDistance: number;
  potentialLoss: number;
}

export interface TakeProfitResult {
  takeProfitPrice: number;
  potentialProfit: number;
  riskRewardRatio: number;
}

/**
 * Calculate position size based on account risk percentage.
 *
 * Formula: position_size = (account * risk%) / (entry - stop_loss)
 *
 * @param accountSize - Total account size
 * @param riskPercentage - Risk percentage (0-100)
 * @param entryPrice - Entry price
 * @param stopLossPrice - Stop loss price
 * @returns Position size and risk metrics
 */
export function calculatePositionSize(
  accountSize: number,
  riskPercentage: number,
  entryPrice: number,
  stopLossPrice: number
): PositionSizeResult {
  const riskAmount = accountSize * (riskPercentage / 100);
  const stopLossDistance = Math.abs(entryPrice - stopLossPrice);

  if (stopLossDistance === 0) {
    return {
      positionSize: 0,
      riskAmount,
      stopLossDistance: 0,
      potentialLoss: 0,
    };
  }

  const positionSize = riskAmount / stopLossDistance;
  const potentialLoss = positionSize * stopLossDistance;

  return {
    positionSize,
    riskAmount,
    stopLossDistance,
    potentialLoss,
  };
}

/**
 * Calculate take profit price for a given risk/reward ratio.
 *
 * @param entryPrice - Entry price
 * @param stopLossPrice - Stop loss price
 * @param riskRewardRatio - Desired risk/reward ratio (e.g., 2 means 2:1)
 * @param isLong - True for long position, false for short
 * @returns Take profit price and potential profit
 */
export function calculateTakeProfit(
  entryPrice: number,
  stopLossPrice: number,
  riskRewardRatio: number,
  isLong: boolean
): TakeProfitResult {
  const risk = Math.abs(entryPrice - stopLossPrice);
  const reward = risk * riskRewardRatio;

  const takeProfitPrice = isLong
    ? entryPrice + reward
    : entryPrice - reward;

  return {
    takeProfitPrice,
    potentialProfit: reward,
    riskRewardRatio,
  };
}

/**
 * Calculate risk/reward ratio for a trade.
 *
 * @param entryPrice - Entry price
 * @param stopLossPrice - Stop loss price
 * @param takeProfitPrice - Take profit price
 * @param isLong - True for long position, false for short
 * @returns Risk/reward ratio
 */
export function calculateRiskRewardRatio(
  entryPrice: number,
  stopLossPrice: number,
  takeProfitPrice: number,
  isLong: boolean
): number {
  const risk = Math.abs(entryPrice - stopLossPrice);

  if (risk === 0) return 0;

  const reward = isLong
    ? takeProfitPrice - entryPrice
    : entryPrice - takeProfitPrice;

  return reward / risk;
}

/**
 * Calculate position size with leverage.
 *
 * @param accountSize - Total account size
 * @param riskPercentage - Risk percentage (0-100)
 * @param entryPrice - Entry price
 * @param stopLossPrice - Stop loss price
 * @param leverage - Leverage multiplier
 * @returns Position size and risk metrics with leverage
 */
export function calculateLeveragedPosition(
  accountSize: number,
  riskPercentage: number,
  entryPrice: number,
  stopLossPrice: number,
  leverage: number
): PositionSizeResult & { effectiveSize: number; marginRequired: number } {
  const baseResult = calculatePositionSize(
    accountSize,
    riskPercentage,
    entryPrice,
    stopLossPrice
  );

  const effectiveSize = baseResult.positionSize * leverage;
  const marginRequired = (effectiveSize * entryPrice) / leverage;

  return {
    ...baseResult,
    effectiveSize,
    marginRequired,
  };
}

/**
 * Calculate potential profit/loss for a position.
 *
 * @param positionSize - Position size (quantity)
 * @param entryPrice - Entry price
 * @param exitPrice - Exit price (current or target)
 * @param isLong - True for long position, false for short
 * @returns Profit/loss amount and percentage
 */
export function calculateProfitLoss(
  positionSize: number,
  entryPrice: number,
  exitPrice: number,
  isLong: boolean
): { amount: number; percentage: number } {
  const priceDiff = isLong ? exitPrice - entryPrice : entryPrice - exitPrice;
  const amount = positionSize * priceDiff;
  const percentage = (priceDiff / entryPrice) * 100;

  return { amount, percentage };
}

/**
 * Format currency value for display.
 */
export function formatCurrency(value: number, decimals: number = 2): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format percentage value for display.
 */
export function formatPercentage(value: number, decimals: number = 2): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`;
}
