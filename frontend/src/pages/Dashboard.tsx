import { useState, useEffect } from 'react'
import type { Company, Page } from '../App'
import { NIFTY50_COMPANIES, INDEX_INSTRUMENTS } from '../App'
import MiniSparkline from '../components/MiniSparkline'
import ApiStatusBanner from '../components/ApiStatusBanner'
import { usePrediction } from '../hooks/usePrediction'
import { useMarketSummary } from '../hooks/useMarketSummary'
import { getWatchlistQuotes } from '../lib/api'
import type { WatchlistQuoteItem } from '../types/api'
import { getMarketStatus, getMarketStatusLabel, getMarketStatusColor, getClosedReason } from '../lib/marketStatus'
import type { MarketStatus } from '../lib/marketStatus'

interface DashboardProps {
  selectedCompany: Company
  onSelectCompany: (company: Company) => void
  onNavigate: (page: Page) => void
}

const trendLevels = ['Strong Bearish', 'Bearish', 'Bullish', 'Strong Bullish']

function fmt(n: number) {
  return new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

export default function Dashboard({ selectedCompany, onSelectCompany, onNavigate }: DashboardProps) {
  const { data: prediction, loading, error } = usePrediction(selectedCompany.ticker)
  const { data: marketSummary } = useMarketSummary()
  const [watchlistQuotes, setWatchlistQuotes] = useState<Record<string, WatchlistQuoteItem>>({})
  const [watchlistLive, setWatchlistLive] = useState<boolean>(false)
  const [marketStatus, setMarketStatus] = useState<MarketStatus>(getMarketStatus())

  // Refresh market status every 60 seconds
  useEffect(() => {
    const interval = setInterval(() => setMarketStatus(getMarketStatus()), 60_000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function fetchWatchlist() {
      try {
        const res = await getWatchlistQuotes()
        if (!cancelled && res?.quotes) {
          setWatchlistQuotes(res.quotes)
          setWatchlistLive(Boolean(res.is_live))
        }
      } catch {
        // Silently retain last known quotes
      }
    }

    fetchWatchlist()
    const interval = setInterval(fetchWatchlist, 45000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  // Fallback (offline / pre-load) derived values, kept from the original mock logic so the
  // UI never goes blank while the first ML response is in flight.
  const isPositive = prediction ? prediction.direction === 'UP' : selectedCompany.changePct >= 0

  const aiRec = prediction?.analytics.ai_recommendation ?? (isPositive ? 'BUY CALL' : 'BUY PUT')
  const trend = prediction?.analytics.market_trend ?? (isPositive ? 'Bullish' : 'Strong Bearish')
  const trendIdx = Math.max(0, trendLevels.indexOf(trend))
  const confidence = prediction?.ai_insights.confidence_pct ?? (isPositive ? 72.4 : 77.1)
  const riskLevel = prediction?.analytics.risk_rating ?? 'LOW'
  const predictedReturn = prediction?.predicted_return_pct ?? (isPositive ? 2.14 : -2.09)
  const tradeScore = prediction?.analytics.trade_score ?? (isPositive ? 82 : 78)
  const atr = prediction?.risk_management.atr_14_points ?? selectedCompany.price * 0.0008
  const stopLoss = prediction?.risk_management.dynamic_stop_loss ??
    (isPositive ? selectedCompany.price - atr * 8 : selectedCompany.price + atr * 8)
  const target = prediction?.risk_management.dynamic_target_price ??
    (isPositive ? selectedCompany.price + atr * 18 : selectedCompany.price - atr * 18)
  const entryZone = prediction?.risk_management.key_levels_guard.suggested_entry_zone
  const entryLow = selectedCompany.price - atr * 1.8
  const entryHigh = selectedCompany.price + atr * 1.8
  const liveQuote = watchlistQuotes[selectedCompany.ticker]
  const currentPrice = liveQuote?.price ?? prediction?.current_price ?? selectedCompany.price
  const priceChange = liveQuote?.change ?? prediction?.change ?? (prediction?.analytics.ltp_change.change ?? selectedCompany.change)
  const priceChangePct = liveQuote?.change_percent ?? prediction?.change_percent ?? (prediction?.analytics.ltp_change.change_pct ?? selectedCompany.changePct)
  const isPriceUp = priceChange >= 0

  const marketIndices = [
    {
      name: 'NIFTY 50',
      ticker: 'NIFTY50',
      value: marketSummary ? fmt(marketSummary.price) : '24,853.15',
      change: marketSummary ? `${marketSummary.change >= 0 ? '+' : ''}${fmt(marketSummary.change)}` : '+112.40',
      pct: marketSummary ? `${marketSummary.change_percent >= 0 ? '+' : ''}${marketSummary.change_percent.toFixed(2)}%` : '+0.45%',
      positive: marketSummary ? marketSummary.change_percent >= 0 : true,
    },
    { name: 'BANKNIFTY', ticker: 'BANKNIFTY', value: '53,284.90', change: '+287.35', pct: '+0.54%', positive: true },
    { name: 'FINNIFTY', ticker: 'FINNIFTY', value: '23,912.60', change: '-45.20', pct: '-0.19%', positive: false },
    { name: 'INDIA VIX', ticker: '', value: '13.42', change: '-0.58', pct: '-4.15%', positive: false },
    { name: 'PCR', ticker: '', value: '0.92', change: '+0.04', pct: '+4.55%', positive: true },
  ]

  const mktColor = getMarketStatusColor(marketStatus)
  const mktLabel = getMarketStatusLabel(marketStatus)

  return (
    <div className="p-4 md:p-6 space-y-5">

      {/* Market Closed Banner */}
      {marketStatus !== 'open' && (
        <div className={`flex items-center gap-3 rounded-2xl px-4 py-3 border ${marketStatus === 'closed' ? 'bg-[#fff5f5] border-[#ffc9c9]' : 'bg-[#fff9db] border-[#ffe8a8]'}`}>
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${mktColor.dot}`} />
          <div className="flex-1">
            <p className={`text-sm font-bold ${mktColor.text}`}>{mktLabel}</p>
            <p className="text-xs text-[#868e96] mt-0.5">
              {getClosedReason()} <span className="text-[#adb5bd]">• Predictions are still active for testing.</span>
            </p>
          </div>
          <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border ${mktColor.bg} ${mktColor.text}`}>
            {mktLabel}
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {marketIndices.map(idx => {
          const indexInstrument = idx.ticker ? INDEX_INSTRUMENTS.find(i => i.ticker === idx.ticker) : null
          return (
            <div
              key={idx.name}
              className={`bg-white border border-[#e9ecef] rounded-2xl p-3 shadow-sm ${indexInstrument ? 'cursor-pointer hover:border-[#1c7ed6]/40 hover:shadow-md transition-all' : ''} ${indexInstrument && selectedCompany.ticker === idx.ticker ? 'ring-2 ring-[#1c7ed6]/30 border-[#1c7ed6]/40' : ''}`}
              onClick={() => {
                if (indexInstrument) onSelectCompany(indexInstrument)
              }}
            >
              <div className="flex items-center gap-1.5 mb-1.5">
                {indexInstrument && <span className="text-[9px]">📊</span>}
                <p className="text-[10px] text-[#868e96] font-medium uppercase tracking-[0.12em]">{idx.name}</p>
              </div>
              <p className="text-sm font-semibold text-[#0f1117] font-mono">{idx.value}</p>
              <div className="flex items-center justify-between mt-2">
                <span className={`text-xs font-mono ${idx.positive ? 'text-[#2f9e44]' : 'text-[#e03131]'}`}>
                  {idx.change} ({idx.pct})
                </span>
                <MiniSparkline positive={idx.positive} width={42} height={18} />
              </div>
            </div>
          )
        })}
      </div>

      <ApiStatusBanner loading={loading} error={error} isLive={prediction?.is_live ?? marketSummary?.is_live} />

      <div className="grid grid-cols-1 xl:grid-cols-[1.6fr_0.85fr] gap-4">
        <div className="space-y-4">
          <div className="bg-white border border-[#e9ecef] rounded-[24px] p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[10px] text-[#868e96] uppercase tracking-[0.18em] font-medium">{selectedCompany.sector}</p>
                <h2 className="text-xl md:text-2xl font-bold text-[#0f1117] mt-1">
                  {selectedCompany.ticker} • {selectedCompany.name}
                </h2>
              </div>
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-[#f3f7fb] text-[#495057] text-[10px] font-semibold uppercase tracking-[0.12em] border border-[#e9ecef]">
                Intraday • 15m
              </span>
            </div>

            <div className="mt-5 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
              <div>
                <p className="text-4xl md:text-5xl font-bold text-[#0f1117] font-mono leading-none">₹{fmt(currentPrice)}</p>
                <div className="mt-2 flex items-center gap-2">
                  <span className={`text-sm md:text-base font-semibold font-mono ${isPriceUp ? 'text-[#2f9e44]' : 'text-[#e03131]'}`}>
                    {isPriceUp ? '+' : ''}{fmt(priceChange)} ({isPriceUp ? '+' : ''}{priceChangePct.toFixed(2)}%)
                  </span>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-[0.12em] ${isPriceUp ? 'bg-[#ebfbee] text-[#2f9e44]' : 'bg-[#fff5f5] text-[#e03131]'}`}>
                    {isPriceUp ? 'UP' : 'DOWN'}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 self-start md:self-auto">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[#f1f3f5] text-[#495057] text-[10px] font-semibold px-2.5 py-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${watchlistLive ? 'bg-[#2f9e44]' : 'bg-[#f59f00]'}`} />
                  {watchlistLive ? 'Live' : 'Syncing'}
                </span>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3 pt-4 border-t border-[#e9ecef]">
              <MetricTile label="Predicted Return" value={`${predictedReturn > 0 ? '+' : ''}${predictedReturn.toFixed(2)}%`} colored />
              <MetricTile label="Trade Score" value={`${tradeScore} / 100`} />
              <MetricTile label="Confidence" value={`${confidence.toFixed(1)}%`} />
              <MetricTile label="Risk Rating" value={riskLevel} colored green={riskLevel === 'LOW'} />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-white border border-[#e9ecef] rounded-2xl p-4 shadow-sm">
              <p className="text-[10px] text-[#868e96] uppercase tracking-[0.18em] font-medium mb-3">Expected Move</p>
              <div className="space-y-2.5">
                <ExpectedRow label="Entry Zone" value={entryZone ?? `₹${fmt(entryLow)} — ₹${fmt(entryHigh)}`} />
                <ExpectedRow label="Target Price" value={`₹${fmt(target)}`} colored={isPositive ? 'green' : 'red'} />
                <ExpectedRow label="Stop Loss" value={`₹${fmt(stopLoss)}`} colored={isPositive ? 'red' : 'green'} />
                <ExpectedRow label="ATR (14)" value={`₹${atr.toFixed(2)} pts`} />
              </div>
            </div>

            <div className="bg-white border border-[#e9ecef] rounded-2xl p-4 shadow-sm">
              <p className="text-[10px] text-[#868e96] uppercase tracking-[0.18em] font-medium mb-3">Market Trend</p>
              <div className="flex flex-col gap-2">
                {trendLevels.map((t, i) => (
                  <div
                    key={t}
                    className={`px-3 py-2 rounded-xl text-xs font-medium transition-colors ${
                      i === trendIdx
                        ? t.includes('Bearish')
                          ? 'bg-[#fff5f5] text-[#e03131] border border-[#e03131]/20'
                          : 'bg-[#ebfbee] text-[#2f9e44] border border-[#2f9e44]/20'
                        : 'bg-[#f8f9fa] text-[#adb5bd] border border-[#eef1f4]'
                    }`}
                  >
                    {i === trendIdx && <span className="mr-1.5">▶</span>}{t}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-white border border-[#e9ecef] rounded-[24px] p-4 shadow-sm">
            <p className="text-[10px] text-[#868e96] uppercase tracking-[0.18em] font-medium mb-3">AI Recommendation</p>
            <div className={`text-center py-4 rounded-2xl mb-3 ${isPositive ? 'bg-[#ebfbee]' : 'bg-[#fff5f5]'}`}>
              <p className={`text-xl font-bold ${isPositive ? 'text-[#2f9e44]' : 'text-[#e03131]'}`}>{aiRec}</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center border border-[#e9ecef] rounded-xl py-2.5 bg-[#fafbfc]">
                <p className="text-[10px] text-[#868e96]">Confidence</p>
                <p className="text-sm font-semibold font-mono text-[#0f1117]">{confidence.toFixed(1)}%</p>
              </div>
              <div className="text-center border border-[#e9ecef] rounded-xl py-2.5 bg-[#fafbfc]">
                <p className="text-[10px] text-[#868e96]">Risk</p>
                <p className="text-sm font-semibold text-[#2f9e44]">{riskLevel}</p>
              </div>
            </div>
          </div>

          <div className="bg-white border border-[#e9ecef] rounded-[24px] p-4 shadow-sm">
            <p className="text-[10px] text-[#868e96] uppercase tracking-[0.18em] font-medium mb-3">Position Snapshot</p>
            <div className="space-y-2.5">
              <TradeRow label="Underlying" value={selectedCompany.ticker} />
              <TradeRow label="Capital" value="₹1,00,000" />
              <TradeRow label="Qty" value="1" />
              <TradeRow label="Strategy" value={aiRec} highlight={!isPositive} />
            </div>
          </div>

          <div className="bg-white border border-[#e9ecef] rounded-[24px] p-4 shadow-sm">
            <p className="text-[10px] text-[#868e96] uppercase tracking-[0.18em] font-medium mb-3">Model Confidence</p>
            <ConfidenceRing value={confidence} />
          </div>
        </div>
      </div>

      <div className="bg-white border border-[#e9ecef] rounded-[24px] overflow-hidden shadow-sm">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#e9ecef]">
          <p className="text-[10px] text-[#868e96] uppercase tracking-[0.18em] font-medium">NIFTY 50 Watchlist</p>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full ${watchlistLive ? 'bg-[#2f9e44] animate-pulse' : 'bg-[#f59f00]'}`}
            />
            <span className="text-[10px] font-medium text-[#495057]">
              {watchlistLive ? 'Real-Time Synced' : 'Syncing Live Data…'}
            </span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#e9ecef] bg-[#fafbfc]">
                <th className="px-4 py-2.5 text-left text-[10px] text-[#868e96] uppercase tracking-[0.12em] font-medium">Ticker</th>
                <th className="px-4 py-2.5 text-left text-[10px] text-[#868e96] uppercase tracking-[0.12em] font-medium hidden sm:table-cell">Company</th>
                <th className="px-4 py-2.5 text-right text-[10px] text-[#868e96] uppercase tracking-[0.12em] font-medium">Price</th>
                <th className="px-4 py-2.5 text-right text-[10px] text-[#868e96] uppercase tracking-[0.12em] font-medium">Chg%</th>
                <th className="px-4 py-2.5 text-center text-[10px] text-[#868e96] uppercase tracking-[0.12em] font-medium">Signal</th>
              </tr>
            </thead>
            <tbody>
              {NIFTY50_COMPANIES.map(company => {
                const liveQuote = watchlistQuotes[company.ticker]
                const displayPrice = liveQuote ? liveQuote.price : company.price
                const displayChange = liveQuote ? liveQuote.change : company.change
                const displayChangePct = liveQuote ? liveQuote.change_percent : company.changePct
                const isItemUp = displayChangePct >= 0

                return (
                  <tr
                    key={company.ticker}
                    onClick={() =>
                      onSelectCompany({
                        ...company,
                        price: displayPrice,
                        change: displayChange,
                        changePct: displayChangePct,
                      })
                    }
                    className={`border-b border-[#e9ecef] cursor-pointer transition-colors hover:bg-[#f8f9fa] ${
                      company.ticker === selectedCompany.ticker ? 'bg-[#f8f9fa]' : ''
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        {company.ticker === selectedCompany.ticker && (
                          <span className="w-1.5 h-1.5 rounded-full bg-[#1c7ed6] inline-block" />
                        )}
                        <span className="font-medium text-[#0f1117]">{company.ticker}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 hidden sm:table-cell text-[#868e96] text-xs">{company.name}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-[#0f1117]">₹{fmt(displayPrice)}</td>
                    <td
                      className={`px-4 py-2.5 text-right font-mono font-medium ${
                        isItemUp ? 'text-[#2f9e44]' : 'text-[#e03131]'
                      }`}
                    >
                      {isItemUp ? '+' : ''}{displayChangePct.toFixed(2)}%
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                          isItemUp ? 'bg-[#ebfbee] text-[#2f9e44]' : 'bg-[#fff5f5] text-[#e03131]'
                        }`}
                      >
                        {isItemUp ? 'BUY CALL' : 'BUY PUT'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function MetricTile({ label, value, sub, colored, green }: { label: string; value: string; sub?: string; colored?: boolean; green?: boolean }) {
  const isNeg = value.startsWith('-')
  return (
    <div className="text-center">
      <p className="text-[10px] text-[#868e96] mb-0.5">{label}</p>
      <p className={`text-sm font-semibold font-mono ${colored ? (green ? 'text-[#2f9e44]' : isNeg ? 'text-[#e03131]' : 'text-[#2f9e44]') : 'text-[#0f1117]'}`}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-[#adb5bd] mt-0.5">{sub}</p>}
    </div>
  )
}

function ExpectedRow({ label, value, colored }: { label: string; value: string; colored?: 'green' | 'red' }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-[#868e96] uppercase tracking-wide">{label}</span>
      <span className={`text-xs font-mono font-medium ${
        colored === 'green' ? 'text-[#2f9e44]' :
        colored === 'red' ? 'text-[#e03131]' :
        'text-[#0f1117]'
      }`}>{value}</span>
    </div>
  )
}

function TradeRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-[#868e96]">{label}</span>
      <span className={`text-xs font-medium ${highlight ? 'text-[#e03131]' : 'text-[#0f1117]'}`}>{value}</span>
    </div>
  )
}

function ConfidenceRing({ value }: { value: number }) {
  const r = 34
  const circumference = 2 * Math.PI * r
  const progress = (value / 100) * circumference
  return (
    <div className="flex items-center justify-center">
      <div className="relative">
        <svg width="88" height="88" viewBox="0 0 88 88">
          <circle cx="44" cy="44" r={r} fill="none" stroke="#e9ecef" strokeWidth="5" />
          <circle
            cx="44" cy="44" r={r}
            fill="none"
            stroke="#1c7ed6"
            strokeWidth="5"
            strokeDasharray={`${progress} ${circumference}`}
            strokeLinecap="round"
            transform="rotate(-90 44 44)"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-bold font-mono text-[#0f1117]">{value.toFixed(0)}%</span>
        </div>
      </div>
    </div>
  )
}
