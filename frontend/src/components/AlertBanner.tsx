import type { TradingAlert } from '../hooks/useAlerts'

interface AlertBannerProps {
  alert: TradingAlert | null
  onDismiss: () => void
}

export default function AlertBanner({ alert, onDismiss }: AlertBannerProps) {
  if (!alert) return null

  const styles = {
    ANALYSIS: {
      panel: 'bg-[#f1f7ff] border-[#b6d4fe]',
      label: 'text-[#1864ab]',
      accent: 'bg-[#339af0]',
      title: 'Live trade guidance',
    },
    PROFIT_LOCK: {
      panel: 'bg-[#ebfbee] border-[#b2f2bb]',
      label: 'text-[#2b8a3e]',
      accent: 'bg-[#37b24d]',
      title: 'Profit protection',
    },
    TRAILING_SL: {
      panel: 'bg-[#e6fcf5] border-[#96f2d7]',
      label: 'text-[#087f5b]',
      accent: 'bg-[#12b886]',
      title: 'Risk adjusted',
    },
    MARKET_CLOSE: {
      panel: 'bg-[#fff9db] border-[#ffe066]',
      label: 'text-[#946c00]',
      accent: 'bg-[#f59f00]',
      title: 'Market close guidance',
    },
    MARKET_CRASH: {
      panel: 'bg-[#fff5f5] border-[#ffc9c9]',
      label: 'text-[#c92a2a]',
      accent: 'bg-[#fa5252]',
      title: 'Market crash',
    },
    STOP_LOSS: {
      panel: 'bg-[#fff5f5] border-[#ffc9c9]',
      label: 'text-[#c92a2a]',
      accent: 'bg-[#fa5252]',
      title: 'Protective exit',
    },
    REVERSAL: {
      panel: 'bg-[#fff5f5] border-[#ffc9c9]',
      label: 'text-[#c92a2a]',
      accent: 'bg-[#fa5252]',
      title: 'Trend reversal',
    },
  }[alert.type] ?? {
    panel: 'bg-[#f8f9fa] border-[#dee2e6]',
    label: 'text-[#495057]',
    accent: 'bg-[#868e96]',
    title: 'Co-Pilot update',
  }

  const smallSummary = (() => {
    const currentPrice = typeof alert.data.current_price === 'number' ? alert.data.current_price : null
    const pnlStatus = typeof alert.data.pnl_status === 'string' ? alert.data.pnl_status : null
    const marketTrend = typeof alert.data.market_trend === 'string' ? alert.data.market_trend : null
    const recommendation = typeof alert.data.recommendation === 'string' ? alert.data.recommendation : null

    const statusText = pnlStatus === 'PROFIT' ? 'Profitable' : pnlStatus === 'LOSS' ? 'Under pressure' : 'Stable'
    const trendText = marketTrend ? ` • ${marketTrend}` : ''
    const priceText = currentPrice !== null ? ` • ₹${currentPrice.toFixed(2)}` : ''
    const recText = recommendation ? ` • ${recommendation}` : ''

    return `${statusText}${priceText}${trendText}${recText}`.replace(/\s{2,}/g, ' ').trim()
  })()

  const eventTime = new Date(alert.timestamp).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className={`mx-4 mt-3 md:mx-6 border rounded px-4 py-3 flex items-start gap-3 ${styles.panel}`}>
      <span className={`w-2 h-2 rounded-full mt-1 shrink-0 ${styles.accent}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p className={`text-[10px] font-bold uppercase tracking-widest ${styles.label}`}>Co-Pilot · {styles.title}</p>
          <span className="text-[10px] text-[#868e96]">{alert.ticker} · {eventTime}</span>
        </div>
        <p className="text-sm font-medium text-[#343a40] mt-1 leading-5">{smallSummary}</p>
      </div>
      <button type="button" onClick={onDismiss} className={`text-xs font-semibold hover:underline shrink-0 ${styles.label}`}>
        Dismiss
      </button>
    </div>
  )
}