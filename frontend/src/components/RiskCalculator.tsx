/**
 * Risk Calculator - Position sizing and risk management calculator
 * 
 * Features:
 * - Position size calculation based on risk %
 * - Stop-loss and take-profit calculator
 * - Risk/reward ratio visualization
 * - Support for leverage
 */

import React, { useState, useEffect } from 'react';
import { useRiskStore } from '../stores/riskStore';
import {
  calculatePositionSize,
  calculateTakeProfit,
  calculateRiskRewardRatio,
  calculateLeveragedPosition,
  formatCurrency,
  formatPercentage,
} from '../lib/risk';

export function RiskCalculator() {
  const {
    accountSize,
    setAccountSize,
    riskPercentage,
    setRiskPercentage,
    entryPrice,
    setEntryPrice,
    stopLossPrice,
    setStopLossPrice,
    takeProfitPrice,
    setTakeProfitPrice,
    isLong,
    setIsLong,
    leverage,
    setLeverage,
    targetRR,
    setTargetRR,
    reset,
  } = useRiskStore();

  // Calculate position size
  const positionResult = leverage > 1
    ? calculateLeveragedPosition(accountSize, riskPercentage, entryPrice, stopLossPrice, leverage)
    : calculatePositionSize(accountSize, riskPercentage, entryPrice, stopLossPrice);

  // Calculate take profit if target R:R is set
  const suggestedTP = calculateTakeProfit(entryPrice, stopLossPrice, targetRR, isLong);

  // Calculate actual R:R if take profit is manually set
  const actualRR = takeProfitPrice
    ? calculateRiskRewardRatio(entryPrice, stopLossPrice, takeProfitPrice, isLong)
    : targetRR;

  // Copy to clipboard helper
  const copyToClipboard = (value: string) => {
    navigator.clipboard.writeText(value);
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f] text-zinc-200 overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Risk Calculator</h1>
        <button
          onClick={reset}
          className="px-3 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded"
        >
          Reset
        </button>
      </div>

      {/* Trade Direction */}
      <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
        <div className="text-xs text-zinc-400 mb-2">Trade Direction</div>
        <div className="flex space-x-2">
          <button
            onClick={() => setIsLong(true)}
            className={`flex-1 py-2 text-sm rounded ${
              isLong ? 'bg-green-600 text-white' : 'bg-zinc-800 text-zinc-400'
            }`}
          >
            LONG
          </button>
          <button
            onClick={() => setIsLong(false)}
            className={`flex-1 py-2 text-sm rounded ${
              !isLong ? 'bg-red-600 text-white' : 'bg-zinc-800 text-zinc-400'
            }`}
          >
            SHORT
          </button>
        </div>
      </div>

      {/* Input Section */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <label className="text-xs text-zinc-400 block mb-1">Account Size ($)</label>
          <input
            type="number"
            value={accountSize}
            onChange={(e) => setAccountSize(parseFloat(e.target.value) || 0)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <label className="text-xs text-zinc-400 block mb-1">Risk per Trade (%)</label>
          <input
            type="number"
            value={riskPercentage}
            onChange={(e) => setRiskPercentage(parseFloat(e.target.value) || 0)}
            step="0.1"
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <label className="text-xs text-zinc-400 block mb-1">Entry Price ($)</label>
          <input
            type="number"
            value={entryPrice}
            onChange={(e) => setEntryPrice(parseFloat(e.target.value) || 0)}
            step="0.01"
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <label className="text-xs text-zinc-400 block mb-1">Stop Loss ($)</label>
          <input
            type="number"
            value={stopLossPrice}
            onChange={(e) => setStopLossPrice(parseFloat(e.target.value) || 0)}
            step="0.01"
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <label className="text-xs text-zinc-400 block mb-1">Leverage (1x = no leverage)</label>
          <input
            type="number"
            value={leverage}
            onChange={(e) => setLeverage(parseFloat(e.target.value) || 1)}
            min="1"
            max="100"
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <label className="text-xs text-zinc-400 block mb-1">Target R:R Ratio</label>
          <input
            type="number"
            value={targetRR}
            onChange={(e) => setTargetRR(parseFloat(e.target.value) || 1)}
            step="0.1"
            min="0.1"
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Results Section */}
      <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
        <h3 className="text-sm font-semibold mb-3">Calculation Results</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-zinc-400 mb-1">Recommended Position Size</div>
            <div className="flex items-center space-x-2">
              <div className="text-lg font-bold text-blue-400">
                {positionResult.positionSize.toFixed(4)}
              </div>
              <button
                onClick={() => copyToClipboard(positionResult.positionSize.toFixed(4))}
                className="text-xs px-2 py-1 bg-zinc-700 hover:bg-zinc-600 rounded"
                title="Copy to clipboard"
              >
                📋
              </button>
            </div>
          </div>

          <div>
            <div className="text-xs text-zinc-400 mb-1">Risk Amount</div>
            <div className="text-lg font-bold text-yellow-400">
              ${formatCurrency(positionResult.riskAmount)}
            </div>
          </div>

          <div>
            <div className="text-xs text-zinc-400 mb-1">Suggested Take Profit</div>
            <div className="text-lg font-bold text-green-400">
              ${suggestedTP.takeProfitPrice.toFixed(2)}
            </div>
          </div>

          <div>
            <div className="text-xs text-zinc-400 mb-1">Potential Profit</div>
            <div className="text-lg font-bold text-green-400">
              ${formatCurrency(suggestedTP.potentialProfit * positionResult.positionSize)}
            </div>
          </div>

          {leverage > 1 && 'marginRequired' in positionResult && (
            <>
              <div>
                <div className="text-xs text-zinc-400 mb-1">Effective Size (with leverage)</div>
                <div className="text-lg font-bold text-purple-400">
                  {'effectiveSize' in positionResult && positionResult.effectiveSize.toFixed(4)}
                </div>
              </div>
              <div>
                <div className="text-xs text-zinc-400 mb-1">Margin Required</div>
                <div className="text-lg font-bold text-purple-400">
                  ${formatCurrency(positionResult.marginRequired)}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Risk/Reward Visual */}
      <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
        <h3 className="text-sm font-semibold mb-3">Risk/Reward Ratio: {actualRR.toFixed(2)}:1</h3>
        <div className="relative h-8 bg-zinc-900 rounded overflow-hidden">
          <div
            className="absolute left-0 top-0 h-full bg-red-500 flex items-center justify-center text-xs font-bold"
            style={{ width: `${(1 / (1 + actualRR)) * 100}%` }}
          >
            {(1 / (1 + actualRR)) * 100 > 15 && 'RISK'}
          </div>
          <div
            className="absolute right-0 top-0 h-full bg-green-500 flex items-center justify-center text-xs font-bold"
            style={{ width: `${(actualRR / (1 + actualRR)) * 100}%` }}
          >
            {(actualRR / (1 + actualRR)) * 100 > 15 && 'REWARD'}
          </div>
        </div>
        <div className="mt-2 flex justify-between text-xs text-zinc-500">
          <span>Loss: ${formatCurrency(positionResult.potentialLoss)}</span>
          <span>Profit: ${formatCurrency(suggestedTP.potentialProfit * positionResult.positionSize)}</span>
        </div>
      </div>
    </div>
  );
}
