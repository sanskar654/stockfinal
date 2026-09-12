import { useState, useEffect, useMemo } from 'react'
import type { Company, Page, TradeInputs } from '../App'
import { NIFTY50_COMPANIES } from '../App'
import ApiStatusBanner from '../components/ApiStatusBanner'
import { usePrediction } from '../hooks/usePrediction'
import { useAuth } from '../context/AuthContext'
import { recordUserTrade, registerActiveTrade } from '../lib/api'
import type { TradeHistoryItem } from '../types/api'

interface RiskManagementProps {
  selectedCompany: Company
  tradeInputs: TradeInputs
  onNavigate: (page: Page) => void
}

type CopilotTone = 'green' | 'yellow' | 'orange' | 'red'

function fmt(n: number) {
  return new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

function getToneClasses(tone: CopilotTone) {
  const tones: Record<CopilotTone, { shell: string; badge: string; text: string; accent: string }> = {
    green: {
      shell: 'border-[#cfe8ff] bg-gradient-to-br from-[#f3f9ff] to-[#ffffff]',
      badge: 'bg-[#e7f5ff] text-[#1971c2]',
      text: 'text-[#1769b0]',
      accent: 'bg-[#1c7ed6]',
    },
    yellow: {
      shell: 'border-[#ffe8a8] bg-gradient-to-br from-[#fff9db] to-[#ffffff]',
      badge: 'bg-[#fff3bf] text-[#b7791f]',
      text: 'text-[#b7791f]',
      accent: 'bg-[#d4a72c]',
    },
    orange: {
      shell: 'border-[#ffd8a8] bg-gradient-to-br from-[#fff4e6] to-[#ffffff]',
      badge: 'bg-[#ffe8cc] text-[#c26d00]',
      text: 'text-[#c26d00]',
      accent: 'bg-[#f08c00]',
    },
    red: {
      shell: 'border-[#ffc9c9] bg-gradient-to-br from-[#fff1f2] to-[#ffffff]',
      badge: 'bg-[#ffe3e3] text-[#c92a2a]',
      text: 'text-[#c92a2a]',
      accent: 'bg-[#e03131]',
    },
  }

  return tones[tone]
}

export default function RiskManagement({ selectedCompany, tradeInputs, onNavigate }: RiskManagementProps) {
  const { currentUser } = useAuth()
  const [isExecuting, setIsExecuting] = useState(false)
  const [executedTrade, setExecutedTrade] = useState<TradeHistoryItem | null>(null)
  const [executionError, setExecutionError] = useState<string | null>(null)
  const [showReasoning, setShowReasoning] = useState(false)
  const [scenarioChange, setScenarioChange] = useState(0)

  const { data: prediction, loading, error } = usePrediction(selectedCompany.ticker, {
    qty: tradeInputs.qty,
    limitPrice: tradeInputs.limitPrice,
  })

  useEffect(() => {
    setExecutedTrade(null)
    setExecutionError(null)
    setShowReasoning(false)
  }, [selectedCompany.ticker, tradeInputs.qty, tradeInputs.limitPrice])

  const isPositive = prediction ? prediction.direction === 'UP' : selectedCompany.changePct >= 0
  const atr = prediction?.risk_management.atr_14_points ?? selectedCompany.price * 0.0008
  const livePrice = prediction?.current_price ?? selectedCompany.price
  const entryPrice = tradeInputs.limitPrice || livePrice
  const currentPnl = (livePrice - entryPrice) * tradeInputs.qty
  const dynamicStopLoss = prediction?.risk_management.dynamic_stop_loss ??
    (isPositive ? selectedCompany.price - atr * 8 : selectedCompany.price + atr * 8)
  const dynamicTarget = prediction?.risk_management.dynamic_target_price ??
    (isPositive ? selectedCompany.price + atr * 18 : selectedCompany.price - atr * 18)

  const tradeScore = prediction?.analytics.trade_score ?? (isPositive ? 82 : 78)
  const confidence = prediction?.ai_insights.confidence_pct ?? (isPositive ? 72.4 : 77.1)
  const predictedReturn = prediction?.predicted_return_pct ?? (isPositive ? 2.14 : -2.09)
  const trend = prediction?.analytics.market_trend ?? (isPositive ? 'Bullish' : 'Strong Bearish')
  const riskRating = prediction?.analytics.risk_rating ?? (predictedReturn >= 0 ? 'LOW' : 'MEDIUM')
  const riskGuardPasses = prediction?.risk_management.passes_risk_reward_guard ?? (predictedReturn >= 0)
  const capitalAllocation = prediction?.risk_management.position_sizing.capital_allocation_pct ?? 100
  const selectedStockRsi = prediction?.risk_management.confluence_guard.rsi_14 ?? prediction?.analytics.momentum.rsi_14 ?? 50
  const marketAverageMove = useMemo(
    () => NIFTY50_COMPANIES.reduce((total, company) => total + company.changePct, 0) / NIFTY50_COMPANIES.length,
    [],
  )

  const bullishBias = prediction ? prediction.direction === 'UP' && predictedReturn > 0 : predictedReturn > 0
  const bearishBias = prediction ? prediction.direction === 'DOWN' && predictedReturn < 0 : predictedReturn < 0
  const recommendationText = prediction?.analytics.ai_recommendation?.toUpperCase() ?? ''
  const isWaitRecommendation = recommendationText.includes('WAIT') || recommendationText.includes('POOR') || recommendationText.includes('PULLBACK') || recommendationText.includes('TREND CONFLICT')
  const isStrongBullishSignal = recommendationText.includes('BUY CALL') || (prediction?.direction === 'UP' && trend.toLowerCase().includes('bullish'))
  const isStrongBearishSignal = recommendationText.includes('BUY PUT') || (prediction?.direction === 'DOWN' && trend.toLowerCase().includes('bearish'))
  const isMarketStress = marketAverageMove <= -1.5 && selectedCompany.changePct <= -1.5

  const copilotTone: CopilotTone = useMemo(() => {
    const isStockWeak = predictedReturn < -1.2 || riskRating === 'HIGH'
    const isStockModerate = riskRating === 'MEDIUM' || selectedStockRsi > 72 || selectedStockRsi < 28
    const isBullishWait = isWaitRecommendation && bullishBias
    const isBearishWait = isWaitRecommendation && bearishBias

    if (capitalAllocation === 0 || (isMarketStress && (selectedCompany.changePct < 0 || !bullishBias))) {
      return 'red'
    }

    if ((prediction && prediction.direction === 'UP' && trend.includes('Strong Bearish')) || (prediction && prediction.direction === 'DOWN' && trend.includes('Strong Bullish'))) {
      return 'red'
    }

    if (isBullishWait || isBearishWait) {
      return 'yellow'
    }

    if (isStockWeak || (isMarketStress && !bullishBias && !bearishBias) || (confidence < 55 && !bullishBias && !bearishBias)) {
      return 'orange'
    }

    if (isStockModerate || marketAverageMove < -0.8) {
      return 'orange'
    }

    if (isStrongBullishSignal || isStrongBearishSignal) {
      return 'green'
    }

    if (riskRating === 'LOW' && predictedReturn >= 0 && confidence >= 60 && capitalAllocation >= 50 && currentPnl >= 0) {
      return 'green'
    }

    return 'yellow'
  }, [bullishBias, capitalAllocation, confidence, currentPnl, isMarketStress, isWaitRecommendation, isStrongBullishSignal, isStrongBearishSignal, marketAverageMove, predictedReturn, riskRating, selectedCompany.changePct, selectedStockRsi, trend, prediction, bearishBias])

  const copilotText: Record<CopilotTone, { label: string; summary: string; guidance: string }> = {
    green: {
      label: 'POSITION STABLE',
      summary: `${selectedCompany.ticker} is holding up well and the broader market is not adding pressure right now.`,
      guidance: 'The setup remains manageable. Keep tighter risk control and avoid adding exposure for now.',
    },
    yellow: {
      label: bullishBias && isWaitRecommendation ? 'WAIT FOR BETTER ENTRY' : 'KEEP AN EYE ON THIS',
      summary: bullishBias && isWaitRecommendation
        ? `${selectedCompany.ticker} is still bullish, but the current entry is weak and the risk/reward is not attractive.`
        : `${selectedCompany.ticker} still looks workable, but momentum is weakening and the market is cooling off.`,
      guidance: bullishBias && isWaitRecommendation
        ? 'The trend is intact, but wait for a cleaner entry near support instead of forcing the trade.'
        : 'Monitor support closely and avoid adding size until the trend improves.',
    },
    orange: {
      label: 'RISK HAS INCREASED',
      summary: `${selectedCompany.ticker} is losing momentum and the wider market is turning weaker.`,
      guidance: 'Review the trade and protect gains instead of adding more risk.',
    },
    red: {
      label: 'ACTION NEEDED',
      summary: `${selectedCompany.ticker} is under pressure and the market is turning risky for this position.`,
      guidance: 'Reduce risk, review the stop-loss, and avoid fresh exposure until the pressure eases.',
    },
  }

  const toneClasses = getToneClasses(copilotTone)

  const marketTone: CopilotTone = useMemo(() => {
    if (riskRating === 'HIGH' || capitalAllocation === 0 || (isMarketStress && selectedCompany.changePct < 0)) return 'red'
    if (isWaitRecommendation || (bullishBias || bearishBias) && !riskGuardPasses) return 'yellow'
    if (riskRating === 'MEDIUM' || marketAverageMove <= -0.8 || selectedStockRsi > 70 || selectedStockRsi < 30) return 'orange'
    if (riskRating === 'LOW' && marketAverageMove <= -0.2) return 'yellow'
    return 'green'
  }, [bullishBias, bearishBias, capitalAllocation, isMarketStress, isWaitRecommendation, marketAverageMove, riskGuardPasses, riskRating, selectedCompany.changePct, selectedStockRsi])

  const marketGuardianText: Record<CopilotTone, string> = {
    green: 'Market conditions are relatively stable for now.',
    yellow: bullishBias && isWaitRecommendation
      ? 'The trend is still bullish, but the current entry quality is weak and should be improved before taking size.'
      : 'Market weakness is increasing and can pressure your stock.',
    orange: 'Market selling has intensified and the risk to your position is rising.',
    red: 'Strong market-wide selling is active and your stock could face heavier downside pressure.',
  }

  const stockVsMarketGap = selectedCompany.changePct - marketAverageMove
  const liveMarketImpact = stockVsMarketGap <= -1.2
    ? `For ${selectedCompany.ticker}, this stock is underperforming the market and the wider move is adding pressure to the position.`
    : stockVsMarketGap >= 1.2
      ? `For ${selectedCompany.ticker}, the stock is outperforming the market and the move is providing support to the position.`
      : bullishBias && isWaitRecommendation
        ? `For ${selectedCompany.ticker}, the trend remains constructive, but the current trade entry is weak because the risk/reward is not attractive enough.`
        : `For ${selectedCompany.ticker}, the stock is tracking the broader market closely, so the current risk is mostly stock-specific rather than market-wide.`

  const scenarioProjectedPrice = livePrice * (1 + scenarioChange / 100)
  const scenarioProjectedPnl = (scenarioProjectedPrice - entryPrice) * tradeInputs.qty
  const scenarioRisk = scenarioProjectedPnl >= 0 ? 'Moderate' : 'High'
  const scenarioStatus = scenarioProjectedPnl >= 0 ? 'Position still favorable' : 'Downside risk growing'

  const handleExecuteTrade = async () => {
    try {
      setIsExecuting(true)
      setExecutionError(null)

      const activeUserId = currentUser?.id || 'usr_demo_trader'
      const tradePayload = {
        user_id: activeUserId,
        ticker: selectedCompany.ticker.toUpperCase(),
        type: (isPositive ? 'BUY' : 'SELL') as 'BUY' | 'SELL',
        qty: tradeInputs.qty,
        price: tradeInputs.limitPrice || selectedCompany.price,
        date: new Date().toISOString().split('T')[0],
      }

      const recorded = await recordUserTrade(tradePayload)
      await registerActiveTrade({
        ticker: selectedCompany.ticker.toUpperCase(),
        entry_price: tradePayload.price,
        qty: tradePayload.qty,
        direction: isPositive ? 'UP' : 'DOWN',
        stop_loss: dynamicStopLoss,
        target_price: dynamicTarget,
      })
      setExecutedTrade(recorded)
    } catch (err: any) {
      console.error('Failed to execute trade:', err)
      setExecutionError(err.message || 'Failed to execute trade. Please try again.')
    } finally {
      setIsExecuting(false)
    }
  }

  const tradeReviewText = executedTrade
    ? `${executedTrade.ticker} was recorded and can be reviewed for missed risk signals in the trade history.`
    : 'Complete and exit a trade to unlock a proper review of missed risk and counterfactual warning points.'

  const support = prediction?.analytics.key_levels.support_20 ?? livePrice * 0.98
  const resistance = prediction?.analytics.key_levels.resistance_20 ?? livePrice * 1.02

  const reasons = [
    `${selectedCompany.ticker} is currently trading at ₹${fmt(livePrice)} and your entry is around ₹${fmt(entryPrice)}.`,
    `The live model is showing ${predictedReturn >= 0 ? 'a positive' : 'a weaker'} short-term outlook with ${confidence.toFixed(1)}% confidence for ${selectedCompany.ticker}.`,
    `${selectedCompany.ticker} is ${stockVsMarketGap >= 0 ? 'outperforming' : 'underperforming'} the broad market by ${Math.abs(stockVsMarketGap).toFixed(2)}%, which matters for the current risk level.`,
    `Your protected level is around ₹${fmt(dynamicStopLoss)} while the near-term target is around ₹${fmt(dynamicTarget)}.`,
  ]

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-[#0f1117]">Risk Management</h1>
          <p className="text-sm text-[#868e96] mt-0.5">
            Focused guidance for {selectedCompany.ticker}
          </p>
        </div>
        <button
          onClick={() => onNavigate('analytics')}
          className="text-sm text-[#1c7ed6] hover:text-[#1971c2] font-medium flex items-center gap-1"
        >
          View Analytics →
        </button>
      </div>

      <ApiStatusBanner loading={loading} error={error} isLive={prediction?.is_live} label="Live prediction unavailable" />

      <div className="bg-white border border-[#e9ecef] rounded p-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <SummaryItem label="Ticker" value={selectedCompany.ticker} mono />
          <SummaryItem label="Company" value={selectedCompany.name} />
          <SummaryItem label="Quantity" value={tradeInputs.qty.toString()} mono />
          <SummaryItem label="Entry" value={`₹${fmt(entryPrice)}`} mono />
          <SummaryItem label="Market Price" value={`₹${fmt(livePrice)}`} mono />
          <SummaryItem
            label="P/L"
            value={`${currentPnl >= 0 ? '+' : '-'}₹${fmt(Math.abs(currentPnl))}`}
            colored={currentPnl >= 0 ? 'green' : 'red'}
          />
        </div>
      </div>

      <div className={`rounded-[22px] border ${toneClasses.shell} p-4 md:p-6 shadow-[0_10px_30px_rgba(15,17,23,0.04)]`}>
        <div className="flex items-center justify-between gap-3 pb-4 border-b border-[#e5e7eb]">
          <div className="flex items-center gap-3">
            <div className={`w-3.5 h-3.5 rounded-full ${toneClasses.accent}`} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#495057]">Co-Pilot</span>
          </div>
          <span className={`inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] ${toneClasses.badge} px-2.5 py-1.5 rounded-full`}>
            <span className={`w-1.5 h-1.5 rounded-full ${toneClasses.accent} animate-pulse`} />
            LIVE
          </span>
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_0.8fr] items-start">
          <div>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <p className="text-[11px] text-[#868e96] uppercase tracking-[0.18em]">{selectedCompany.ticker} — {selectedCompany.name}</p>
              <span className="text-[10px] text-[#868e96] font-medium">Updated just now</span>
            </div>
            <div className="mt-3">
              <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.18em] ${toneClasses.badge}`}>
                {copilotText[copilotTone].label}
              </span>
            </div>
            <h2 className={`mt-3 text-[1.15rem] md:text-[1.75rem] font-bold leading-tight ${toneClasses.text}`}>
              {copilotText[copilotTone].summary}
            </h2>
            <p className="mt-2 text-sm text-[#495057] leading-6 max-w-2xl">
              {copilotText[copilotTone].guidance}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
            <MiniStat label="Current Price" value={`₹${fmt(livePrice)}`} />
            <MiniStat label="Protected At" value={`₹${fmt(dynamicStopLoss)}`} />
            <MiniStat label="Target" value={`₹${fmt(dynamicTarget)}`} />
            <MiniStat label="P/L" value={`${currentPnl >= 0 ? '+' : '-'}₹${fmt(Math.abs(currentPnl))}`} colored={currentPnl >= 0 ? 'green' : 'red'} />
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button className="px-3 py-2 text-xs font-semibold rounded-xl border border-[#dfe3e8] bg-white text-[#0f1117] hover:bg-[#f8f9fa] shadow-sm">
            Review Position
          </button>
          <button
            onClick={() => setShowReasoning(v => !v)}
            className="px-3 py-2 text-xs font-semibold rounded-xl border border-[#dfe3e8] bg-white text-[#0f1117] hover:bg-[#f8f9fa] shadow-sm"
          >
            {showReasoning ? 'Hide reasons' : 'Why am I seeing this?'}
          </button>
        </div>

        {showReasoning && (
          <div className="mt-4 rounded-xl border border-[#e9ecef] bg-white/70 p-3 text-sm text-[#495057]">
            <p className="font-semibold text-[#0f1117] mb-2">Why am I seeing this?</p>
            <ul className="space-y-2">
              {reasons.map((reason, index) => (
                <li key={index} className="flex gap-2">
                  <span className="mt-1 text-[#2f9e44]">✓</span>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
            <div className="mt-3 pt-3 border-t border-[#e9ecef] text-xs text-[#868e96]">
              <p className="font-semibold text-[#0f1117] mb-1">Technical details</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <div>RSI: {prediction?.analytics.momentum.rsi_14?.toFixed(1) ?? 'n/a'}</div>
                <div>MACD: {prediction?.analytics.momentum.macd_status ?? 'n/a'}</div>
                <div>Support: ₹{fmt(support)}</div>
                <div>Resistance: ₹{fmt(resistance)}</div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className={`rounded-2xl border ${getToneClasses(marketTone).shell} p-4`}>
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#495057]">Market Guardian</p>
            <h3 className={`mt-1 text-xl font-bold ${getToneClasses(marketTone).text}`}>
              {marketTone === 'green' ? 'NORMAL' : marketTone === 'yellow' ? 'CAUTION' : marketTone === 'orange' ? 'HIGH RISK' : 'MARKET STRESS'}
            </h3>
          </div>
          <span className={`inline-flex items-center px-2.5 py-1 text-[10px] font-bold uppercase rounded-full ${getToneClasses(marketTone).badge}`}>
            {marketGuardianText[marketTone]}
          </span>
        </div>

        <p className="mt-3 text-sm text-[#495057] leading-6">
          {marketGuardianText[marketTone]} For {selectedCompany.ticker}, this means {liveMarketImpact}
        </p>
      </div>

      <div className="bg-white border border-[#e9ecef] rounded-2xl p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#495057]">Scenario Simulator</p>
            <h3 className="mt-1 text-xl font-bold text-[#0f1117]">What if the stock moves?</h3>
          </div>
          <span className="text-xs text-[#868e96]">Estimated scenario</span>
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-[#868e96] mb-2">
            <span>Stock change</span>
            <span className="font-semibold text-[#0f1117]">{scenarioChange > 0 ? '+' : ''}{scenarioChange}%</span>
          </div>
          <input
            type="range"
            min={-5}
            max={5}
            step={1}
            value={scenarioChange}
            onChange={(event) => setScenarioChange(Number(event.target.value))}
            className="w-full accent-[#1c7ed6]"
          />
          <div className="mt-2 flex justify-between text-[10px] text-[#868e96]">
            <span>-5%</span>
            <span>0%</span>
            <span>+5%</span>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <MiniStat label="Estimated Price" value={`₹${fmt(scenarioProjectedPrice)}`} />
          <MiniStat label="Estimated P/L" value={`${scenarioProjectedPnl >= 0 ? '+' : '-'}₹${fmt(Math.abs(scenarioProjectedPnl))}`} tone={scenarioProjectedPnl >= 0 ? 'green' : 'red'} />
          <MiniStat label="Risk Level" value={scenarioRisk} tone={scenarioProjectedPnl >= 0 ? 'yellow' : 'red'} />
          <MiniStat label="Distance from SL" value={`₹${fmt(Math.abs(scenarioProjectedPrice - dynamicStopLoss))}`} />
        </div>

        <p className="mt-3 text-sm text-[#495057]">
          {scenarioStatus}. This is an estimated scenario, not a prediction.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <OutputCard label="Dynamic Stop Loss" value={`₹${fmt(dynamicStopLoss)}`} colored="red" sub="dynamic_stop_loss" />
        <OutputCard label="Dynamic Target" value={`₹${fmt(dynamicTarget)}`} colored="green" sub="dynamic_target_price" />
        <OutputCard label="ATR 14" value={`₹${atr.toFixed(4)}`} sub="atr_14_points" />
        <OutputCard label="Risk/Reward Ratio" value={prediction?.risk_management.risk_reward_ratio ?? '1:2.25'} sub="risk_reward_ratio" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white border border-[#e9ecef] rounded p-4">
          <p className="text-[10px] text-[#868e96] uppercase tracking-widest font-medium mb-3">Order Analysis</p>
          <div className="space-y-2">
            <PSRow label="Required Capital" value={`₹${fmt(prediction?.groww_order_analysis.required_capital ?? (tradeInputs.limitPrice * tradeInputs.qty))}`} />
            <PSRow label="Custom Profit Potential" value={`₹${fmt(prediction?.groww_order_analysis.custom_profit_potential ?? Math.abs(dynamicTarget - tradeInputs.limitPrice) * tradeInputs.qty)}`} colored="green" />
            <PSRow label="Custom Maximum Risk" value={`₹${fmt(prediction?.groww_order_analysis.custom_max_risk ?? Math.abs(dynamicStopLoss - tradeInputs.limitPrice) * tradeInputs.qty)}`} colored="red" />
            <PSRow label="Custom R/R Ratio" value={prediction?.groww_order_analysis.custom_rr_ratio ?? '2.25'} />
          </div>
        </div>

        <div className="bg-white border border-[#e9ecef] rounded p-4">
          <p className="text-[10px] text-[#868e96] uppercase tracking-widest font-medium mb-3">Position Sizing</p>
          <div className="space-y-2">
            <PSRow label="Capital Allocation" value={prediction?.risk_management.position_sizing.capital_allocation_pct !== undefined ? `${prediction.risk_management.position_sizing.capital_allocation_pct}%` : '10%'} />
            <PSRow label="Position Size" value={prediction?.risk_management.position_sizing.position_size_label ?? '10% Capital Allocation'} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <OutputCard label="Trade Score" value={`${tradeScore} / 100`} sub="Overall score" />
        <OutputCard label="Confidence" value={`${confidence.toFixed(1)}%`} sub="Model confidence" />
        <OutputCard label="Predicted Return" value={`${predictedReturn > 0 ? '+' : ''}${predictedReturn.toFixed(2)}%`} sub="ML forecast" colored={predictedReturn >= 0 ? 'green' : 'red'} />
        <OutputCard label="Market Trend" value={trend} sub="Classification" colored={isPositive ? 'green' : 'red'} />
      </div>

      <div className="bg-white border border-[#e9ecef] rounded p-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${executedTrade ? 'bg-[#2b8a3e]' : 'bg-[#1971c2]'}`}></span>
              <h3 className="text-sm font-bold text-[#0f1117]">Order Execution Control</h3>
              <span className="text-[10px] px-2 py-0.5 bg-[#f1f3f5] text-[#495057] font-mono font-medium rounded">
                {selectedCompany.ticker} • {tradeInputs.qty} share{tradeInputs.qty === 1 ? '' : 's'} @ ₹{fmt(tradeInputs.limitPrice || selectedCompany.price)}
              </span>
            </div>
            <p className="text-xs text-[#868e96] mt-1">
              {executedTrade
                ? 'Order confirmed and saved to the local trade ledger. You can view it under Trade History in your Profile.'
                : 'Clicking Execute Trade will record this order into your Trade History. If you leave without clicking, no trade will be stored.'}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {executedTrade ? (
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#2b8a3e] bg-[#ebfbee] border border-[#b2f2bb] px-3 py-2 rounded">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                  Executed ({executedTrade.ticker})
                </span>
                <button
                  type="button"
                  onClick={() => onNavigate('profile')}
                  className="px-4 py-2 text-xs font-semibold text-white bg-[#1971c2] hover:bg-[#1864ab] rounded transition-colors flex items-center gap-1.5 shadow-xs cursor-pointer"
                >
                  View in Profile →
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleExecuteTrade}
                disabled={isExecuting || loading}
                className="px-5 py-2 text-xs font-bold text-white bg-[#2b8a3e] hover:bg-[#237032] active:bg-[#1e5e2a] disabled:opacity-50 rounded transition-colors flex items-center gap-2 shadow-xs cursor-pointer"
              >
                {isExecuting ? (
                  <>
                    <svg className="animate-spin h-3.5 w-3.5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                    </svg>
                    <span>Executing Trade...</span>
                  </>
                ) : (
                  <>
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
                    <span>EXECUTE TRADE</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {executionError && (
          <div className="mt-3 p-2.5 bg-[#fff5f5] text-[#e03131] border border-[#ffc9c9] rounded text-xs flex items-center justify-between">
            <span>{executionError}</span>
            <button
              type="button"
              onClick={() => setExecutionError(null)}
              className="text-[#e03131] font-bold text-xs hover:underline ml-2 cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function SummaryItem({ label, value, mono, colored }: { label: string; value: string; mono?: boolean; colored?: 'green' | 'red' }) {
  return (
    <div>
      <p className="text-[10px] text-[#868e96] mb-0.5">{label}</p>
      <p className={`text-sm font-medium ${mono ? 'font-mono' : ''} ${
        colored === 'green' ? 'text-[#2f9e44]' :
        colored === 'red' ? 'text-[#e03131]' :
        'text-[#0f1117]'
      }`}>{value}</p>
    </div>
  )
}

function OutputCard({ label, value, sub, colored, badge, badgeGreen }: {
  label: string; value: string; sub?: string; colored?: 'green' | 'red'; badge?: string; badgeGreen?: boolean
}) {
  return (
    <div className="bg-white border border-[#e9ecef] rounded p-3">
      <p className="text-[10px] text-[#868e96] uppercase tracking-wide font-medium mb-1">{label}</p>
      <p className={`text-sm font-semibold font-mono ${
        colored === 'green' ? 'text-[#2f9e44]' :
        colored === 'red' ? 'text-[#e03131]' :
        'text-[#0f1117]'
      }`}>{value}</p>
      {sub && <p className="text-[10px] text-[#adb5bd] mt-0.5">{sub}</p>}
      {badge && (
        <span className={`inline-block mt-1.5 text-[9px] px-2 py-0.5 rounded font-medium ${
          badgeGreen ? 'bg-[#ebfbee] text-[#2f9e44]' : 'bg-[#fff5f5] text-[#e03131]'
        }`}>{badge}</span>
      )}
    </div>
  )
}

function PSRow({ label, value, colored }: { label: string; value: string; colored?: 'green' | 'red' }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-[#f1f3f5] last:border-0">
      <span className="text-xs text-[#868e96]">{label}</span>
      <span className={`text-xs font-mono font-medium ${
        colored === 'green' ? 'text-[#2f9e44]' :
        colored === 'red' ? 'text-[#e03131]' :
        'text-[#0f1117]'
      }`}>{value}</span>
    </div>
  )
}

function MiniStat({ label, value, tone }: { label: string; value: string; tone?: 'green' | 'red' | 'yellow' }) {
  const textColor = tone === 'green'
    ? 'text-[#2f9e44]'
    : tone === 'red'
      ? 'text-[#e03131]'
      : tone === 'yellow'
        ? 'text-[#b7791f]'
        : 'text-[#0f1117]'

  return (
    <div className="rounded-xl border border-[#e9ecef] bg-white/80 p-2.5">
      <p className="text-[10px] uppercase tracking-[0.14em] text-[#868e96]">{label}</p>
      <p className={`mt-1 text-sm font-bold font-mono ${textColor}`}>{value}</p>
    </div>
  )
}
