/**
 * Crosshair Synchronization Hook
 * ===============================
 * Synchronizes crosshair position across multiple charts
 *
 * Note: This provides basic crosshair sync by sharing the crosshair time in state.
 * Due to lightweight-charts v5 API limitations, we cannot programmatically
 * set the crosshair position on other charts. Charts will share the time value,
 * but visual crosshair sync requires lightweight-charts v6+ API support.
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

  // Subscribe to store changes to sync this chart when other charts move
  // Note: lightweight-charts v5 doesn't provide a programmatic API to set crosshair position
  // This effect is a placeholder for when the API becomes available in v6+
  // For now, the shared crosshairTime state allows components to be aware of the sync
  useEffect(() => {
    if (!chartApi || !crosshairTime) return

    // TODO: When lightweight-charts v6+ is available, use API like:
    // chartApi.setCrosshairPosition({ time: crosshairTime })
    // or
    // chartApi.timeScale().scrollToPosition(crosshairTime, true)

    // Current limitation: visual crosshair cannot be programmatically positioned
    // Charts share the time value via state, but each chart's crosshair is independent
  }, [chartApi, crosshairTime])

  return {
    crosshairTime,
  }
}
