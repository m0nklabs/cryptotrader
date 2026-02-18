/**
 * Equity Curve Chart Component
 * =============================
 * Visualize backtest equity progression over time
 */

import { useEffect, useRef } from 'react'

type Props = {
  equityCurve: number[]
  initialCapital: number
}

export default function EquityCurve({ equityCurve, initialCapital }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Set canvas size
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * window.devicePixelRatio
    canvas.height = rect.height * window.devicePixelRatio
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio)

    const width = rect.width
    const height = rect.height
    const padding = 40

    // Clear canvas
    ctx.clearRect(0, 0, width, height)

    if (equityCurve.length === 0) {
      ctx.fillStyle = '#71717a'
      ctx.font = '14px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('No equity data', width / 2, height / 2)
      return
    }

    // Calculate min/max for scaling
    const minEquity = Math.min(...equityCurve)
    const maxEquity = Math.max(...equityCurve)
    const equityRange = maxEquity - minEquity || 1

    // Draw grid
    ctx.strokeStyle = '#27272a'
    ctx.lineWidth = 1
    for (let i = 0; i <= 4; i++) {
      const y = padding + (i * (height - 2 * padding)) / 4
      ctx.beginPath()
      ctx.moveTo(padding, y)
      ctx.lineTo(width - padding, y)
      ctx.stroke()
    }

    // Draw equity curve
    ctx.strokeStyle = '#3b82f6'
    ctx.lineWidth = 2
    ctx.beginPath()

    equityCurve.forEach((equity, idx) => {
      const x = padding + (idx / (equityCurve.length - 1)) * (width - 2 * padding)
      const y = height - padding - ((equity - minEquity) / equityRange) * (height - 2 * padding)

      if (idx === 0) {
        ctx.moveTo(x, y)
      } else {
        ctx.lineTo(x, y)
      }
    })
    ctx.stroke()

    // Draw initial capital line
    ctx.strokeStyle = '#71717a'
    ctx.lineWidth = 1
    ctx.setLineDash([5, 5])
    const initialY = height - padding - ((initialCapital - minEquity) / equityRange) * (height - 2 * padding)
    ctx.beginPath()
    ctx.moveTo(padding, initialY)
    ctx.lineTo(width - padding, initialY)
    ctx.stroke()
    ctx.setLineDash([])

    // Draw labels
    ctx.fillStyle = '#71717a'
    ctx.font = '11px sans-serif'
    ctx.textAlign = 'right'

    // Y-axis labels
    for (let i = 0; i <= 4; i++) {
      const value = maxEquity - (i * equityRange) / 4
      const y = padding + (i * (height - 2 * padding)) / 4
      ctx.fillText(`$${value.toFixed(0)}`, padding - 5, y + 4)
    }

    // X-axis labels
    ctx.textAlign = 'center'
    ctx.fillText('Start', padding, height - 10)
    ctx.fillText('End', width - padding, height - 10)
  }, [equityCurve, initialCapital])

  return (
    <div className="bg-[#1a1a2e] p-4 rounded border border-zinc-700">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Equity Curve</h3>
      <canvas
        ref={canvasRef}
        className="w-full h-64 bg-[#0f0f1e] rounded"
        style={{ width: '100%', height: '256px' }}
      />
    </div>
  )
}
