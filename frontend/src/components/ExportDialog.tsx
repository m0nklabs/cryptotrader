import React, { useState } from 'react';
import { Download, FileText, FileJson } from 'lucide-react';
import { downloadBlob } from '../lib/download';

interface ExportDialogProps {
  onClose: () => void;
}

type ExportType = 'candles' | 'trades' | 'portfolio';
type ExportFormat = 'csv' | 'json';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function ExportDialog({ onClose }: ExportDialogProps) {
  const [exportType, setExportType] = useState<ExportType>('candles');
  const [format, setFormat] = useState<ExportFormat>('csv');
  const [symbol, setSymbol] = useState('BTCUSD');
  const [exchange, setExchange] = useState('bitfinex');
  const [timeframe, setTimeframe] = useState('1h');
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async () => {
    setIsExporting(true);

    try {
      let url = '';

      if (exportType === 'candles') {
        url = `${API_BASE_URL}/export/candles?symbol=${encodeURIComponent(symbol)}&exchange=${encodeURIComponent(exchange)}&timeframe=${encodeURIComponent(timeframe)}&format=${encodeURIComponent(format)}`;
      } else if (exportType === 'trades') {
        url = `${API_BASE_URL}/export/trades?format=${encodeURIComponent(format)}`;
      } else if (exportType === 'portfolio') {
        url = `${API_BASE_URL}/export/portfolio?format=${encodeURIComponent(format)}`;
      }

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Export failed');
      }

      // Get filename from Content-Disposition header or generate one
      const contentDisposition = response.headers.get('Content-Disposition');
      const filenameMatch = contentDisposition?.match(/filename="?(.+)"?/);
      const filename = filenameMatch?.[1] || `export_${Date.now()}.${format}`;

      // Download the file using shared helper
      const blob = await response.blob();
      downloadBlob(blob, filename);

      onClose();
    } catch (error) {
      console.error('Export error:', error);
      alert('Export failed. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700 w-full max-w-md">
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Export Data</h2>

        <div className="space-y-4">
          {/* Export Type */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-2">Export Type</label>
            <select
              value={exportType}
              onChange={(e) => setExportType(e.target.value as ExportType)}
              className="w-full bg-gray-800 text-gray-300 rounded px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-blue-500"
            >
              <option value="candles">Candles (OHLCV)</option>
              <option value="trades">Trade History</option>
              <option value="portfolio">Portfolio Snapshot</option>
            </select>
          </div>

          {/* Format */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-2">Format</label>
            <div className="flex gap-2">
              <button
                onClick={() => setFormat('csv')}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded text-sm transition-colors ${
                  format === 'csv'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                <FileText className="w-4 h-4" />
                CSV
              </button>
              <button
                onClick={() => setFormat('json')}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded text-sm transition-colors ${
                  format === 'json'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                <FileJson className="w-4 h-4" />
                JSON
              </button>
            </div>
          </div>

          {/* Candles-specific options */}
          {exportType === 'candles' && (
            <>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-2">Symbol</label>
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="w-full bg-gray-800 text-gray-300 rounded px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-blue-500"
                  placeholder="BTCUSD"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-2">Exchange</label>
                <select
                  value={exchange}
                  onChange={(e) => setExchange(e.target.value)}
                  className="w-full bg-gray-800 text-gray-300 rounded px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-blue-500"
                >
                  <option value="bitfinex">Bitfinex</option>
                  <option value="binance">Binance</option>
                  <option value="coinbase">Coinbase</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-2">Timeframe</label>
                <select
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="w-full bg-gray-800 text-gray-300 rounded px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-blue-500"
                >
                  <option value="1m">1 minute</option>
                  <option value="5m">5 minutes</option>
                  <option value="15m">15 minutes</option>
                  <option value="1h">1 hour</option>
                  <option value="4h">4 hours</option>
                  <option value="1d">1 day</option>
                </select>
              </div>
            </>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2 mt-6">
          <button
            onClick={onClose}
            disabled={isExporting}
            className="flex-1 px-4 py-2 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isExporting ? (
              <>Processing...</>
            ) : (
              <>
                <Download className="w-4 h-4" />
                Export
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
