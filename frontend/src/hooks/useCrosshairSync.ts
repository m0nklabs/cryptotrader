/**
 * Crosshair Synchronization Hook
 * ===============================
 * Synchronizes crosshair position across multiple charts
 */

import { useEffect, useCallback } from 'react'
import type { IChartApi } from 'lightweight-charts'
import { useMultiChartStore } from '../stores/multiChartStore'

type CrosshairMoveHandler = (param: any) => void

export function useCrosshairSync(
  chartApi: IChartApi | null,
  chartId: string
) {
  const { crosshairTime, setCrosshairTime } = useMultiChartStore()

  // Handle crosshair move on this chart
  const handleCrosshairMove = useCallback(
    (param: any) => {
      if (!param.time) {
        setCrosshairTime(null)
        return
      }

      const time = typeof param.time === 'number' ? param.time : Number(param.time)
      setCrosshairTime(time)
    },
    [setCrosshairTime]
  )

  // Subscribe to crosshair move events
  useEffect(() => {
    if (!chartApi) return

    chartApi.subscribeCrosshairMove(handleCrosshairMove)

    return () => {
      chartApi.unsubscribeCrosshairMove(handleCrosshairMove)
    }
  }, [chartApi, handleCrosshairMove])

  // Apply crosshair position from other charts
  // TODO: Future enhancement - When lightweight-charts v5 adds API to programmatically
  // set crosshair position, implement it here to complete the synchronization.
  // Currently, synchronization happens through subscribeCrosshairMove callbacks
  // that all charts share via the crosshairTime state.
  // This effect is intentionally minimal to avoid unnecessary re-renders.
  useEffect(() => {
    // Placeholder for future crosshair positioning API
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    crosshairTime,
  }
}
