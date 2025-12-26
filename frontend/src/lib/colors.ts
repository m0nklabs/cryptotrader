/**
 * Color Utilities
 * ===============
 * Color scales and utilities for visualizations
 */

/**
 * Get color for correlation heatmap
 * @param correlation Value between -1 and 1
 * @returns CSS color string
 */
export function getCorrelationColor(correlation: number): string {
  // Clamp to [-1, 1]
  const value = Math.max(-1, Math.min(1, correlation))

  if (value > 0) {
    // Positive correlation: white to green
    const intensity = Math.round(value * 255)
    return `rgb(34, ${155 + intensity / 2}, 94)` // Tailwind green-500 base
  } else if (value < 0) {
    // Negative correlation: white to red
    const intensity = Math.round(Math.abs(value) * 255)
    return `rgb(${155 + intensity / 2}, 68, 68)` // Tailwind red-500 base
  } else {
    // Zero correlation: white/gray
    return 'rgb(156, 163, 175)' // Tailwind gray-400
  }
}

/**
 * Get heatmap color scale (for legends)
 */
export function getCorrelationColorScale(): Array<{ value: number; color: string }> {
  return [
    { value: -1.0, color: getCorrelationColor(-1.0) },
    { value: -0.5, color: getCorrelationColor(-0.5) },
    { value: 0.0, color: getCorrelationColor(0.0) },
    { value: 0.5, color: getCorrelationColor(0.5) },
    { value: 1.0, color: getCorrelationColor(1.0) },
  ]
}

/**
 * Format correlation value for display
 */
export function formatCorrelation(value: number): string {
  return value.toFixed(3)
}
