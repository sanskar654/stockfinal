import type { TradingAlert } from '../hooks/useAlerts'
import type { Page } from '../App'

interface AlertBannerProps {
  alert: TradingAlert | null
  onDismiss: () => void
  onNavigate?: (page: Page) => void
}

function fmt(n: number) {
  return new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

export default function AlertBanner({ alert, onDismiss, onNavigate }: AlertBannerProps) {
  if (!alert) return null

  const isProfit = alert.type === 'PROFIT_LOCK' || alert.data?.pnl_status === 'PROFIT'
  const isLoss = alert.type === 'STOP_LOSS' || alert.type === 'REVERSAL' || alert.type === 'MARKET_CRASH'
  const isTrailing = alert.type === 'TRAILING_SL'

  const styles = {
    PROFIT_LOCK: {
      panel: 'bg-gradient-to-r from-[#ebfbee] via-[#f4fbf6] to-white border-[#b2f2bb]',
      badge: 'bg-[#2b8a3e] text-white',
      title: 'TARGET REACHED · PROFIT LOCK',
      accent: '#2b8a3e',
    },
    TRAILING_SL: {
      panel: 'bg-gradient-to-r from-[#e6fcf5] via-[#f0fdf9] to-white border-[#96f2d7]',
      badge: 'bg-[#087f5b] text-white',
      title: 'TRAILING STOP-LOSS UPDATED',
      accent: '#087f5b',
    },
    STOP_LOSS: {
      panel: 'bg-gradient-to-r from-[#fff5f5] via-[#fff8f8] to-white border-[#ffc9c9]',
      badge: 'bg-[#e03131] text-white',
      title: 'PROTECTIVE STOP-LOSS TRIGGERED',
      accent: '#e03131',
    },
    REVERSAL: {
      panel: 'bg-gradient-to-r from-[#fff5f5] via-[#fff8f8] to-white border-[#ffc9c9]',
      badge: 'bg-[#c92a2a] text-white',
      title: 'TREND REVERSAL DETECTED',
      accent: '#c92a2a',
    },
    MARKET_CRASH: {
      panel: 'bg-gradient-to-r from-[#fff5f5] via-[#fff8f8] to-white border-[#ffc9c9]',
      badge: 'bg-[#c92a2a] text-white',
      title: 'MARKET ALERT · DEFENSIVE ACTION',
      accent: '#c92a2a',
    },
    ANALYSIS: {
      panel: isProfit
        ? 'bg-gradient-to-r from-[#ebfbee] via-[#f4fbf6] to-white border-[#b2f2bb]'
        : isLoss
          ? 'bg-gradient-to-r from-[#fff5f5] via-[#fff8f8] to-white border-[#ffc9c9]'
          : 'bg-gradient-to-r from-[#e7f5ff] via-[#f0f8ff] to-white border-[#a5d8ff]',
      badge: isProfit
        ? 'bg-[#2b8a3e] text-white'
        : isLoss
          ? 'bg-[#e03131] text-white'
          : 'bg-[#1971c2] text-white',
      title: isProfit
        ? 'ACTIVE TRADE · IN PROFIT'
        : isLoss
          ? 'ACTIVE TRADE · RISK BUFFER ACTIVE'
          : 'AI COPILOT · TRADE GUIDANCE',
      accent: isProfit ? '#2b8a3e' : isLoss ? '#e03131' : '#1971c2',
    },
  }[alert.type] ?? {
    panel: 'bg-gradient-to-r from-[#f8f9fa] via-white to-white border-[#dee2e6]',
    badge: 'bg-[#495057] text-white',
    title: 'AI COPILOT NOTIFICATION',
    accent: '#495057',
  }

  const currentPrice = typeof alert.data?.current_price === 'number' ? alert.data.current_price : null
  const unrealizedPnl = typeof alert.data?.unrealized_pnl === 'number' ? alert.data.unrealized_pnl : null
  const pnlPct = typeof alert.data?.pnl_pct === 'number' ? alert.data.pnl_pct : null
  const stopLoss = typeof alert.data?.stop_loss === 'number' ? alert.data.stop_loss : typeof alert.data?.new_stop_loss === 'number' ? alert.data.new_stop_loss : null
  const targetPrice = typeof alert.data?.target_price === 'number' ? alert.data.target_price : null
  const recommendation = typeof alert.data?.recommendation === 'string' ? alert.data.recommendation : null
  const trend = typeof alert.data?.market_trend === 'string' ? alert.data.market_trend : null

  const eventTime = new Date(alert.timestamp).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className={`mx-4 mt-3 md:mx-6 border rounded-2xl p-4 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-3 ${styles.panel}`}>
      <div className="flex items-start gap-3 min-w-0 flex-1">
        <span className="w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 animate-pulse" style={{ backgroundColor: styles.accent }} />
        
        <div className="min-w-0 flex-1">
          {/* Header Strip */}
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${styles.badge}`}>
              {styles.title}
            </span>
            <span className="text-xs font-bold text-[#0f1117] font-mono">
              {alert.ticker}
            </span>
            <span className="text-[10px] text-[#868e96]">
              {eventTime}
            </span>

            {/* Live Price Tag */}
            {currentPrice !== null && (
              <span className="text-xs font-mono font-semibold text-[#495057] bg-white/80 border border-black/5 px-2 py-0.5 rounded">
                Live: ₹{fmt(currentPrice)}
              </span>
            )}

            {/* PnL Tag */}
            {unrealizedPnl !== null && (
              <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${unrealizedPnl >= 0 ? 'bg-[#ebfbee] text-[#2b8a3e]' : 'bg-[#fff5f5] text-[#e03131]'}`}>
                {unrealizedPnl >= 0 ? '+' : ''}₹{fmt(unrealizedPnl)} {pnlPct !== null ? `(${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)` : ''}
              </span>
            )}
          </div>

          {/* Broker Guidance Message */}
          <p className="text-xs md:text-sm text-[#343a40] mt-1.5 font-medium leading-relaxed">
            {alert.message || (
              <>
                {trend && <span>Trend: <strong className="text-[#0f1117]">{trend}</strong>. </span>}
                {stopLoss !== null && <span>Stop-Loss active at <strong className="font-mono text-[#e03131]">₹{fmt(stopLoss)}</strong>. </span>}
                {targetPrice !== null && <span>Target: <strong className="font-mono text-[#2b8a3e]">₹{fmt(targetPrice)}</strong>. </span>}
                {recommendation && <span className="text-[#1971c2] font-semibold">{recommendation}</span>}
              </>
            )}
          </p>
        </div>
      </div>

      {/* Action CTA & Dismiss */}
      <div className="flex items-center gap-2 self-end md:self-center shrink-0">
        {onNavigate && (
          <button
            type="button"
            onClick={() => onNavigate('risk-management')}
            className="text-xs font-semibold text-[#1971c2] bg-white hover:bg-[#e7f5ff] border border-[#a5d8ff] px-3 py-1.5 rounded-lg transition-colors cursor-pointer shadow-2xs"
          >
            Manage Risk →
          </button>
        )}
        <button
          type="button"
          onClick={onDismiss}
          className="text-xs font-medium text-[#868e96] hover:text-[#495057] px-2 py-1 rounded hover:bg-black/5 transition-colors cursor-pointer"
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}