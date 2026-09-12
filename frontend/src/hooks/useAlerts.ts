import { useEffect, useMemo, useState } from 'react'

export interface TradingAlert {
  type: string
  trade_id: number
  ticker: string
  message: string
  timestamp: string
  data: Record<string, unknown>
}

function getWebSocketUrl(): string {
  const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '')
  if (configuredBase) {
    return configuredBase.replace(/^http/, 'ws') + '/ws/alerts'
  }
  return `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/alerts`
}

export function useAlerts(selectedTicker?: string): TradingAlert | null {
  const [allAlerts, setAllAlerts] = useState<TradingAlert[]>([])

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let stopped = false

    const connect = () => {
      if (stopped) return
      socket = new WebSocket(getWebSocketUrl())
      socket.onmessage = event => {
        try {
          const parsed = JSON.parse(event.data) as TradingAlert
          setAllAlerts(current => [parsed, ...current].slice(0, 30))
        } catch {
          // Ignore malformed server messages and keep the stream alive.
        }
      }
      socket.onclose = () => {
        if (!stopped) reconnectTimer = window.setTimeout(connect, 5000)
      }
      socket.onerror = () => socket?.close()
    }

    connect()
    return () => {
      stopped = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  const latestAlert = useMemo(() => {
    if (!allAlerts.length) return null
    if (!selectedTicker) return allAlerts[0]

    const currentTickerAlert = allAlerts.find(alert =>
      alert.ticker?.toUpperCase() === selectedTicker.toUpperCase(),
    )
    if (currentTickerAlert) return currentTickerAlert

    const marketWideAlert = allAlerts.find(alert =>
      alert.type === 'MARKET_CRASH' || alert.type === 'REVERSAL' || alert.type === 'STOP_LOSS'
    )

    return marketWideAlert ?? allAlerts[0]
  }, [allAlerts, selectedTicker])

  return latestAlert
}