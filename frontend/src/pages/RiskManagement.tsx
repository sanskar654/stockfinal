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

type SignalType = 'BUY' | 'SELL' | 'WAIT'

function fmt(n: number) {
  return new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

/** SVG semi-circular risk gauge */
function RiskGauge({ level }: { level: 'LOW' | 'MEDIUM' | 'HIGH' }) {
  const pct = level === 'LOW' ? 25 : level === 'MEDIUM' ? 60 : 90
  const color = level === 'LOW' ? '#2f9e44' : level === 'MEDIUM' ? '#d97706' : '#e03131'
  const r = 38
  const circ = Math.PI * r
  const strokeDashoffset = circ * (1 - pct / 100)

  return (
    <div className="flex flex-col items-center">
      <svg width="90" height="50" viewBox="0 0 100 54">
        <path
          d="M 12 48 A 38 38 0 0 1 88 48"
          fill="none" stroke="#e9ecef" strokeWidth="8" strokeLinecap="round"
        />
        <path
          d="M 12 48 A 38 38 0 0 1 88 48"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={strokeDashoffset}
          style={{ transition: 'stroke-dashoffset 0.8s ease, stroke 0.4s ease' }}
        />
        <circle cx="50" cy="48" r="3" fill={color} />
      </svg>
      <span className="text-[10px] font-bold uppercase tracking-wider mt-0.5" style={{ color }}>
        {level} RISK
      </span>
    </div>
  )
}

/** Visual Price Ladder: SL → Entry Zone → Live Price → 30m Target → EOD Target */
function PriceLadder({
  sl,
  entry,
  current,
  target30m,
  targetEod,
}: {
  sl: number
  entry: number
  current: number
  target30m: number
  targetEod: number
}) {
  const values = [sl, entry, current, target30m, targetEod].filter(v => Number.isFinite(v) && v > 0)
  const min = Math.min(...values) * 0.997
  const max = Math.max(...values) * 1.003
  const range = max - min || 1
  const pct = (v: number) => Math.max(4, Math.min(96, ((v - min) / range) * 100))

  return (
    <div className="w-full pt-2 pb-6">
      <div className="relative h-3 bg-gradient-to-r from-[#ffe3e3] via-[#e7f5ff] to-[#d3f9d8] rounded-full my-6">
        {/* Stop Loss Marker */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 flex flex-col items-center" style={{ left: `${pct(sl)}%` }}>
          <div className="w-4 h-4 rounded-full bg-[#e03131] border-2 border-white shadow-md ring-2 ring-[#e03131]/30" />
          <div className="absolute top-5 flex flex-col items-center whitespace-nowrap">
            <span className="text-[10px] font-bold text-[#e03131]">Stop Loss</span>
            <span className="text-[10px] font-mono font-bold text-[#e03131]">₹{fmt(sl)}</span>
          </div>
        </div>

        {/* Entry Price Marker */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 flex flex-col items-center" style={{ left: `${pct(entry)}%` }}>
          <div className="w-4 h-4 rounded-full bg-[#1c7ed6] border-2 border-white shadow-md ring-2 ring-[#1c7ed6]/30" />
          <div className="absolute -top-7 flex flex-col items-center whitespace-nowrap">
            <span className="text-[10px] font-bold text-[#1c7ed6]">Entry Price</span>
            <span className="text-[10px] font-mono font-bold text-[#1c7ed6]">₹{fmt(entry)}</span>
          </div>
        </div>

        {/* Live Price Marker */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 flex flex-col items-center" style={{ left: `${pct(current)}%` }}>
          <div className="w-3.5 h-3.5 rounded-full bg-[#343a40] border-2 border-white shadow" />
          <div className="absolute top-5 flex flex-col items-center whitespace-nowrap">
            <span className="text-[9px] font-bold text-[#495057]">Live LTP</span>
            <span className="text-[9px] font-mono font-bold text-[#495057]">₹{fmt(current)}</span>
          </div>
        </div>

        {/* 30m Target Marker */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 flex flex-col items-center" style={{ left: `${pct(target30m)}%` }}>
          <div className="w-4 h-4 rounded-full bg-[#2b8a3e] border-2 border-white shadow-md ring-2 ring-[#2b8a3e]/30" />
          <div className="absolute -top-7 flex flex-col items-center whitespace-nowrap">
            <span className="text-[10px] font-bold text-[#2b8a3e]">30m Target</span>
            <span className="text-[10px] font-mono font-bold text-[#2b8a3e]">₹{fmt(target30m)}</span>
          </div>
        </div>

        {/* EOD Target Marker */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 flex flex-col items-center" style={{ left: `${pct(targetEod)}%` }}>
          <div className="w-3.5 h-3.5 rounded-full bg-[#1971c2] border-2 border-white shadow-md ring-2 ring-[#1971c2]/30" />
          <div className="absolute top-5 flex flex-col items-center whitespace-nowrap">
            <span className="text-[10px] font-bold text-[#1971c2]">EOD Target</span>
            <span className="text-[10px] font-mono font-bold text-[#1971c2]">₹{fmt(targetEod)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function RiskManagement({ selectedCompany, tradeInputs, onNavigate }: RiskManagementProps) {
  const { currentUser } = useAuth()
  const [isExecuting, setIsExecuting] = useState(false)
  const [executedTrade, setExecutedTrade] = useState<TradeHistoryItem | null>(null)
  const [executionError, setExecutionError] = useState<string | null>(null)
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false)
  const [scenarioChange, setScenarioChange] = useState(0)

  // Quantity from trade inputs or default 10
  const quantity = Math.max(1, tradeInputs.qty || 1)

  const { data: prediction, loading, error } = usePrediction(selectedCompany.ticker, {
    qty: quantity,
    limitPrice: tradeInputs.limitPrice,
    pollIntervalMs: 30000,
  })

  useEffect(() => {
    setExecutedTrade(null)
    setExecutionError(null)
    setScenarioChange(0)
  }, [selectedCompany.ticker, quantity, tradeInputs.limitPrice])

  // ── 1. Core Price Data ────────────────────────────────────────────────────────
  const isPositive = prediction ? prediction.direction === 'UP' : selectedCompany.changePct >= 0
  const livePrice = prediction?.current_price ?? selectedCompany.price
  const entryPrice = tradeInputs.limitPrice && tradeInputs.limitPrice > 0 ? tradeInputs.limitPrice : livePrice

  // ── 2. Real Protective Levels & Price Targets ────────────────────────────────
  const atr = prediction?.risk_management?.atr_14_points ?? (livePrice * 0.008)
  const rawStopLoss = prediction?.risk_management?.dynamic_stop_loss ?? (isPositive ? livePrice - atr * 1.5 : livePrice + atr * 1.5)
  const rawTarget30m = prediction?.ai_insights?.target_price_30m ?? prediction?.risk_management?.dynamic_target_price ?? (isPositive ? livePrice + atr * 2.8 : livePrice - atr * 2.8)
  const rawTargetEod = prediction?.ai_insights?.target_price_eod ?? (isPositive ? livePrice * 1.018 : livePrice * 0.982)

  const dynamicStopLoss = Math.round(rawStopLoss * 100) / 100
  const dynamicTarget = Math.round(rawTarget30m * 100) / 100
  const dynamicTargetEod = Math.round(rawTargetEod * 100) / 100

  // ── 3. Exact Calculations Scaled by Quantity ─────────────────────────────────
  const requiredCapital = entryPrice * quantity

  // Risk per share & Total Risk
  const riskPerShare = Math.max(0.1, Math.abs(entryPrice - dynamicStopLoss))
  const totalMaxRisk = riskPerShare * quantity
  const riskPctOfCapital = (riskPerShare / entryPrice) * 100

  // Reward per share & Total Reward (30m target)
  const rewardPerShare = Math.max(0.1, Math.abs(dynamicTarget - entryPrice))
  const totalProfitPotential = rewardPerShare * quantity
  const rewardPctOfCapital = (rewardPerShare / entryPrice) * 100

  // Full Day EOD Potential
  const rewardPerShareEod = Math.max(0.1, Math.abs(dynamicTargetEod - entryPrice))
  const totalProfitPotentialEod = rewardPerShareEod * quantity
  const rewardPctEod = (rewardPerShareEod / entryPrice) * 100

  // Risk / Reward ratio
  const calculatedRr = rewardPerShare / (riskPerShare || 1)
  const riskRewardRatio = `1 : ${calculatedRr.toFixed(2)}`
  const riskGuardPasses = calculatedRr >= 0.9

  // Technical Indicators
  const rsi = prediction?.risk_management?.confluence_guard?.rsi_14 ?? prediction?.analytics?.momentum?.rsi_14 ?? 52
  const volumeRatio = prediction?.risk_management?.confluence_guard?.volume_ratio_20 ?? prediction?.analytics?.volume_strength?.volume_ratio_20 ?? 1.15
  const confidence = prediction?.ai_insights?.confidence_pct ?? 75
  const predictedReturn = prediction?.predicted_return_pct ?? (isPositive ? 1.4 : -1.2)
  const trend = prediction?.analytics?.market_trend ?? (isPositive ? 'Bullish' : 'Bearish')
  const riskRating = (prediction?.analytics?.risk_rating ?? (confidence >= 60 ? 'LOW' : 'MEDIUM')) as 'LOW' | 'MEDIUM' | 'HIGH'
  const entryZone = prediction?.ai_insights?.suggested_entry_zone ?? `₹${fmt(entryPrice * 0.998)} - ₹${fmt(entryPrice * 1.002)}`
  const capitalAllocation = prediction?.risk_management?.position_sizing?.capital_allocation_pct ?? 100

  // ── 4. Accurate Broker Signal Evaluation ───────────────────────────────────
  const signalType: SignalType = useMemo(() => {
    // 1. Bearish / Downside signals (RED)
    if (prediction?.direction === 'DOWN' && predictedReturn < 0) {
      return 'SELL'
    }

    // 2. Extreme Overbought Caution (ORANGE / AMBER)
    // Only wait if RSI is overbought (> 75) where buying would chase the peak, or allocation is 0%
    if (rsi > 75 || capitalAllocation === 0 || confidence < 45) {
      return 'WAIT'
    }

    // 3. Bullish / Long opportunities (GREEN) - includes oversold bounce & upward continuation
    if (prediction?.direction === 'UP' || predictedReturn >= 0 || isPositive) {
      return 'BUY'
    }

    return 'BUY'
  }, [prediction?.direction, predictedReturn, isPositive, rsi, confidence, capitalAllocation])

  // Copilot Tone Data
  const toneData = useMemo(() => {
    if (signalType === 'BUY') {
      return {
        badgeBg: 'bg-[#ebfbee] text-[#2b8a3e] border-[#b2f2bb]',
        badgeText: '🟢 BUY SIGNAL (LONG SETUP)',
        border: 'border-[#b2f2bb]',
        cardBg: 'bg-gradient-to-br from-[#f6fff8] via-[#f0fff4] to-white',
        accentColor: '#2b8a3e',
        headline: `High Probability Bullish Opportunity for ${selectedCompany.ticker}`,
        summary: `The ML model forecasts a +${Math.abs(predictedReturn).toFixed(2)}% upside move toward ₹${fmt(dynamicTarget)} with ${confidence.toFixed(1)}% model confidence. ${rsi < 35 ? `RSI at ${rsi.toFixed(1)} indicates a strong oversold bounce setup.` : `The ${trend} trend aligns with the long setup.`}`,
        actionPlan: [
          `Entry Zone: Buy between ${entryZone} (LTP is ₹${fmt(livePrice)}).`,
          `Stop Loss: Maintain hard stop-loss at ₹${fmt(dynamicStopLoss)} (Risk: ₹${fmt(riskPerShare)}/share).`,
          `Target: Take 50% profit at ₹${fmt(dynamicTarget)} (+${rewardPctOfCapital.toFixed(2)}%), trail remainder to EOD target ₹${fmt(dynamicTargetEod)}.`,
        ],
      }
    }
    if (signalType === 'SELL') {
      return {
        badgeBg: 'bg-[#fff5f5] text-[#c92a2a] border-[#ffc9c9]',
        badgeText: '🔴 BEARISH / SELL SIGNAL (SHORT / PUT)',
        border: 'border-[#ffc9c9]',
        cardBg: 'bg-gradient-to-br from-[#fff8f8] via-[#fff5f5] to-white',
        accentColor: '#c92a2a',
        headline: `Bearish Downside Warning for ${selectedCompany.ticker}`,
        summary: `The ML model predicts a ${predictedReturn.toFixed(2)}% downward continuation. Selling pressure and downside momentum indicated.`,
        actionPlan: [
          `Long Positions: Avoid fresh buying. Exit if holding long.`,
          `Short / Put Entry: If trading options, Put target is ₹${fmt(dynamicTarget)}.`,
          `Protective Stop: Set stop-loss at ₹${fmt(dynamicStopLoss)} to guard against bounces.`,
        ],
      }
    }
    // WAIT / CAUTION
    return {
      badgeBg: 'bg-[#fff9db] text-[#b7791f] border-[#ffe8a8]',
      badgeText: '🟡 WAIT FOR PULLBACK (CAUTION)',
      border: 'border-[#ffe8a8]',
      cardBg: 'bg-gradient-to-br from-[#fffdf5] via-[#fff9db]/30 to-white',
      accentColor: '#d97706',
      headline: `Consolidation / Overbought Range for ${selectedCompany.ticker}`,
      summary: rsi > 75
        ? `RSI is overbought (${rsi.toFixed(1)}). The stock has surged quickly; wait for a pullback to the entry zone before deploying fresh capital.`
        : `Model confidence is consolidating (${confidence.toFixed(1)}%). Wait for price to test the entry support zone before committing capital.`,
      actionPlan: [
        `Do not chase price at current market high.`,
        `Wait for price to retest entry support at ${entryZone}.`,
        `Risk/Reward improves substantially upon pullback entry.`,
      ],
    }
  }, [signalType, selectedCompany.ticker, predictedReturn, dynamicTarget, confidence, trend, entryZone, livePrice, dynamicStopLoss, riskPerShare, rewardPctOfCapital, dynamicTargetEod, rsi])

  // ── 5. Scenario Simulator Math ───────────────────────────────────────────────
  const scenarioPrice = entryPrice * (1 + scenarioChange / 100)
  const scenarioPnlPerShare = scenarioPrice - entryPrice
  const scenarioTotalPnl = scenarioPnlPerShare * quantity
  const isScenarioStopHit = isPositive ? scenarioPrice <= dynamicStopLoss : scenarioPrice >= dynamicStopLoss
  const isScenarioTargetHit = isPositive ? scenarioPrice >= dynamicTarget : scenarioPrice <= dynamicTarget

  // ── 6. Execute Trade Handler ─────────────────────────────────────────────────
  const handleExecuteTrade = async () => {
    try {
      setIsExecuting(true)
      setExecutionError(null)

      const activeUserId = currentUser?.id || 'usr_demo_trader'
      const tradePayload = {
        user_id: activeUserId,
        ticker: selectedCompany.ticker.toUpperCase(),
        type: (signalType === 'SELL' ? 'SELL' : 'BUY') as 'BUY' | 'SELL',
        qty: quantity,
        price: entryPrice,
        date: new Date().toISOString().split('T')[0],
      }

      const recorded = await recordUserTrade(tradePayload)
      await registerActiveTrade({
        ticker: selectedCompany.ticker.toUpperCase(),
        entry_price: tradePayload.price,
        qty: tradePayload.qty,
        direction: signalType === 'SELL' ? 'DOWN' : 'UP',
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

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3 pb-2 border-b border-[#e9ecef]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-[#0f1117]">Risk Management & Copilot</h1>
            <span className="text-xs font-bold text-[#1c7ed6] bg-[#e7f5ff] border border-[#a5d8ff] px-2.5 py-0.5 rounded-full font-mono">
              {selectedCompany.ticker}
            </span>
          </div>
          <p className="text-xs text-[#868e96] mt-0.5">
            Real-time protective stop-loss, targets, and quantity-scaled risk calculator for <strong className="text-[#0f1117] font-semibold">{quantity} share{quantity > 1 ? 's' : ''}</strong>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate('analytics')}
            className="text-xs font-semibold text-[#1c7ed6] bg-white border border-[#a5d8ff] rounded-lg px-3 py-1.5 hover:bg-[#e7f5ff] transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
          >
            📊 View Technical Analytics →
          </button>
        </div>
      </div>

      <ApiStatusBanner loading={loading} error={error} isLive={prediction?.is_live} label="Live ML pipeline connected" />

      {/* ── 1. TOP HERO: REAL PRICE TARGETS & PROTECTIVE LEVELS (NUMBERS FIRST) ── */}
      <div className="bg-white border-2 border-[#1c7ed6]/20 rounded-2xl p-5 shadow-sm space-y-4 bg-gradient-to-b from-white via-white to-[#f8f9fa]">
        <div className="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-[#e9ecef]">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#2b8a3e] animate-pulse" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-[#0f1117]">
              Key Protective Levels & Targets (First Priority)
            </h2>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-[#868e96]">Suggested Entry Zone:</span>
            <span className="font-mono font-bold text-[#1c7ed6] bg-[#e7f5ff] border border-[#a5d8ff] px-2 py-0.5 rounded">
              {entryZone}
            </span>
          </div>
        </div>

        {/* 5 Big Number Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          
          {/* Card 1: Live LTP */}
          <div className="bg-[#f8f9fa] border border-[#dee2e6] rounded-xl p-3.5 flex flex-col justify-between">
            <span className="text-[11px] font-bold text-[#868e96] uppercase tracking-wider">Live LTP</span>
            <p className="text-xl font-bold font-mono text-[#0f1117] my-1">₹{fmt(livePrice)}</p>
            <span className="text-[10px] text-[#868e96]">Entry set @ ₹{fmt(entryPrice)}</span>
          </div>

          {/* Card 2: Dynamic Stop Loss */}
          <div className="bg-[#fff5f5] border-2 border-[#ffa8a8] rounded-xl p-3.5 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#e03131] uppercase tracking-wider">🛡️ Stop Loss</span>
              <span className="text-[10px] font-bold bg-white text-[#e03131] px-1.5 py-0.5 rounded border border-[#ffc9c9]">
                -{riskPctOfCapital.toFixed(2)}%
              </span>
            </div>
            <p className="text-xl font-bold font-mono text-[#e03131] my-1">₹{fmt(dynamicStopLoss)}</p>
            <span className="text-[10px] text-[#e03131] font-medium">Risk: -₹{fmt(riskPerShare)}/sh (-₹{fmt(totalMaxRisk)} total)</span>
          </div>

          {/* Card 3: 30m Target */}
          <div className="bg-[#ebfbee] border-2 border-[#8ce99a] rounded-xl p-3.5 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#2b8a3e] uppercase tracking-wider">🎯 30m Target</span>
              <span className="text-[10px] font-bold bg-white text-[#2b8a3e] px-1.5 py-0.5 rounded border border-[#b2f2bb]">
                +{rewardPctOfCapital.toFixed(2)}%
              </span>
            </div>
            <p className="text-xl font-bold font-mono text-[#2b8a3e] my-1">₹{fmt(dynamicTarget)}</p>
            <span className="text-[10px] text-[#2b8a3e] font-medium">Gain: +₹{fmt(rewardPerShare)}/sh (+₹{fmt(totalProfitPotential)} total)</span>
          </div>

          {/* Card 4: EOD Target */}
          <div className="bg-[#e7f5ff] border border-[#a5d8ff] rounded-xl p-3.5 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#1971c2] uppercase tracking-wider">📈 EOD Target</span>
              <span className="text-[10px] font-bold bg-white text-[#1971c2] px-1.5 py-0.5 rounded border border-[#a5d8ff]">
                +{rewardPctEod.toFixed(2)}%
              </span>
            </div>
            <p className="text-xl font-bold font-mono text-[#1971c2] my-1">₹{fmt(dynamicTargetEod)}</p>
            <span className="text-[10px] text-[#1971c2]">Full session swing target</span>
          </div>

          {/* Card 5: Risk / Reward */}
          <div className="bg-[#f8f9fa] border border-[#dee2e6] rounded-xl p-3.5 flex flex-col justify-between">
            <span className="text-[11px] font-bold text-[#495057] uppercase tracking-wider">⚖️ Risk / Reward</span>
            <p className="text-xl font-bold font-mono text-[#0f1117] my-1">{riskRewardRatio}</p>
            <span className="text-[10px] font-bold text-[#2b8a3e]">
              {riskGuardPasses ? '✓ Favorable Setup' : '⚠️ Moderate Setup'}
            </span>
          </div>

        </div>

        {/* Visual Ladder */}
        <PriceLadder
          sl={dynamicStopLoss}
          entry={entryPrice}
          current={livePrice}
          target30m={dynamicTarget}
          targetEod={dynamicTargetEod}
        />
      </div>

      {/* ── 2. INNOVATIVE AI RISK CO-PILOT (FRIENDLY & ACCURATE GUIDANCE) ─── */}
      <div className={`rounded-2xl border ${toneData.border} ${toneData.cardBg} p-5 shadow-xs transition-all`}>
        <div className="flex items-start justify-between gap-4 flex-wrap pb-3 border-b border-black/5">
          <div className="flex items-center gap-2.5">
            <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full border shadow-2xs ${toneData.badgeBg}`}>
              {toneData.badgeText}
            </span>
            <span className="text-xs font-medium text-[#495057]">
              Model Confidence: <strong className="font-mono text-[#0f1117]">{confidence.toFixed(1)}%</strong>
            </span>
            <span className="text-xs text-[#868e96]">• {selectedCompany.sector}</span>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-[#868e96]">Risk Score:</span>
            <span className={`text-xs font-bold px-2 py-0.5 rounded ${riskRating === 'LOW' ? 'bg-[#ebfbee] text-[#2b8a3e]' : riskRating === 'MEDIUM' ? 'bg-[#fff9db] text-[#b7791f]' : 'bg-[#fff5f5] text-[#c92a2a]'}`}>
              {riskRating} RISK
            </span>
          </div>
        </div>

        <div className="mt-4 grid lg:grid-cols-[1fr_240px] gap-6 items-center">
          <div>
            <h3 className="text-lg md:text-xl font-bold text-[#0f1117] tracking-tight">
              {toneData.headline}
            </h3>
            <p className="text-sm text-[#495057] mt-1 leading-relaxed">
              {toneData.summary}
            </p>

            {/* Structured 3-Step Execution Action Plan */}
            <div className="mt-4 bg-white/90 border border-black/10 rounded-xl p-4 shadow-2xs space-y-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-[#495057] mb-1">
                📋 Step-by-Step AI Execution Plan
              </p>
              {toneData.actionPlan.map((step, idx) => (
                <div key={idx} className="flex items-start gap-2.5 text-xs md:text-sm text-[#0f1117]">
                  <span className="w-5 h-5 rounded-full bg-[#1c7ed6] text-white text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                    {idx + 1}
                  </span>
                  <span className="leading-snug">{step}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Right mini gauge & allocation */}
          <div className="bg-white/90 border border-black/10 rounded-xl p-4 flex flex-col items-center justify-center space-y-2 text-center shadow-2xs">
            <RiskGauge level={riskRating} />
            <div className="w-full pt-2 border-t border-[#e9ecef] flex justify-between text-xs text-[#495057]">
              <span>Max Sizing:</span>
              <strong className="text-[#2b8a3e]">{capitalAllocation}% Allocation</strong>
            </div>
            <div className="w-full flex justify-between text-xs text-[#495057]">
              <span>Trend Bias:</span>
              <strong className="font-semibold text-[#0f1117]">{trend}</strong>
            </div>
          </div>
        </div>
      </div>

      {/* ── 3. QUANTITY-SCALED CAPITAL & P/L BREAKDOWN (EXACT MATH) ─────── */}
      <div className="bg-white border border-[#e9ecef] rounded-2xl p-5 shadow-xs">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-4 pb-3 border-b border-[#e9ecef]">
          <div>
            <h3 className="text-base font-bold text-[#0f1117] flex items-center gap-2">
              <span>💰</span> Position Risk & Capital Allocation (Quantity Scaled)
            </h3>
            <p className="text-xs text-[#868e96]">
              Precise monetary values for <strong className="text-[#1c7ed6] font-mono font-bold">{quantity} share{quantity > 1 ? 's' : ''}</strong> at ₹{fmt(entryPrice)}
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs bg-[#f8f9fa] px-3 py-1.5 rounded-lg border border-[#e9ecef]">
            <span className="text-[#868e96]">Order Volume:</span>
            <strong className="text-[#0f1117] font-mono">{quantity} units</strong>
          </div>
        </div>

        {/* 4 Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          
          <div className="bg-[#f8f9fa] border border-[#e9ecef] rounded-xl p-4">
            <p className="text-[11px] font-bold uppercase tracking-wider text-[#868e96]">Total Capital Required</p>
            <p className="text-xl font-bold font-mono text-[#0f1117] mt-1">₹{fmt(requiredCapital)}</p>
            <p className="text-xs text-[#868e96] mt-1">
              {quantity} share{quantity > 1 ? 's' : ''} × ₹{fmt(entryPrice)}
            </p>
          </div>

          <div className="bg-[#fff5f5] border border-[#ffc9c9] rounded-xl p-4">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider text-[#e03131]">Max Potential Risk</p>
              <span className="text-[10px] font-bold text-[#e03131] bg-white px-1.5 py-0.5 rounded border border-[#ffc9c9]">
                -{riskPctOfCapital.toFixed(2)}%
              </span>
            </div>
            <p className="text-xl font-bold font-mono text-[#e03131] mt-1">-₹{fmt(totalMaxRisk)}</p>
            <p className="text-xs text-[#868e96] mt-1">
              At Stop Loss ₹{fmt(dynamicStopLoss)} (-₹{fmt(riskPerShare)}/sh)
            </p>
          </div>

          <div className="bg-[#ebfbee] border border-[#b2f2bb] rounded-xl p-4">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider text-[#2b8a3e]">30m Target Profit</p>
              <span className="text-[10px] font-bold text-[#2b8a3e] bg-white px-1.5 py-0.5 rounded border border-[#b2f2bb]">
                +{rewardPctOfCapital.toFixed(2)}%
              </span>
            </div>
            <p className="text-xl font-bold font-mono text-[#2b8a3e] mt-1">+₹{fmt(totalProfitPotential)}</p>
            <p className="text-xs text-[#868e96] mt-1">
              At Target ₹{fmt(dynamicTarget)} (+₹{fmt(rewardPerShare)}/sh)
            </p>
          </div>

          <div className="bg-[#e7f5ff] border border-[#a5d8ff] rounded-xl p-4">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider text-[#1c7ed6]">Full Session EOD Profit</p>
              <span className="text-[10px] font-bold text-[#1c7ed6] bg-white px-1.5 py-0.5 rounded border border-[#a5d8ff]">
                +{rewardPctEod.toFixed(2)}%
              </span>
            </div>
            <p className="text-xl font-bold font-mono text-[#1c7ed6] mt-1">+₹{fmt(totalProfitPotentialEod)}</p>
            <p className="text-xs text-[#868e96] mt-1">
              At Target ₹{fmt(dynamicTargetEod)} (+₹{fmt(rewardPerShareEod)}/sh)
            </p>
          </div>

        </div>

        {/* Clean Side-by-Side Comparison Table */}
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="border-b border-[#e9ecef] bg-[#f8f9fa] text-[#495057] font-semibold">
                <th className="py-2.5 px-3">Price Level</th>
                <th className="py-2.5 px-3">Price / Share</th>
                <th className="py-2.5 px-3">Per 1 Share Outcome</th>
                <th className="py-2.5 px-3 font-bold text-[#0f1117]">Total for {quantity} Shares</th>
                <th className="py-2.5 px-3">Trading Rule</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e9ecef] text-[#495057]">
              <tr>
                <td className="py-2.5 px-3 font-medium text-[#0f1117]">Your Entry Price</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#1c7ed6]">₹{fmt(entryPrice)}</td>
                <td className="py-2.5 px-3 font-mono">₹{fmt(entryPrice)}</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#0f1117]">₹{fmt(requiredCapital)}</td>
                <td className="py-2.5 px-3 text-[#868e96]">Entry Zone: {entryZone}</td>
              </tr>
              <tr className="bg-[#fff5f5]/60">
                <td className="py-2.5 px-3 font-medium text-[#e03131]">Dynamic Stop Loss</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#e03131]">₹{fmt(dynamicStopLoss)}</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#e03131]">-₹{fmt(riskPerShare)}</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#e03131]">-₹{fmt(totalMaxRisk)}</td>
                <td className="py-2.5 px-3 text-[#e03131]">Hard exit if breached (ATR buffer)</td>
              </tr>
              <tr className="bg-[#ebfbee]/60">
                <td className="py-2.5 px-3 font-medium text-[#2b8a3e]">Target 1 (30-Min)</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#2b8a3e]">₹{fmt(dynamicTarget)}</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#2b8a3e]">+₹{fmt(rewardPerShare)}</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#2b8a3e]">+₹{fmt(totalProfitPotential)}</td>
                <td className="py-2.5 px-3 text-[#2b8a3e]">Book 50% partial profit here</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-medium text-[#1c7ed6]">Target 2 (End of Day)</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#1c7ed6]">₹{fmt(dynamicTargetEod)}</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#1c7ed6]">+₹{fmt(rewardPerShareEod)}</td>
                <td className="py-2.5 px-3 font-mono font-bold text-[#1c7ed6]">+₹{fmt(totalProfitPotentialEod)}</td>
                <td className="py-2.5 px-3 text-[#868e96]">Trail stop loss to lock gains</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ── 4. WHAT-IF SCENARIO SIMULATOR (REAL RUPEE OUTCOMES) ─────────── */}
      <div className="bg-white border border-[#e9ecef] rounded-2xl p-5 shadow-xs space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="text-base font-bold text-[#0f1117] flex items-center gap-1.5">
              <span>🎛️</span> Interactive Scenario Simulator
            </h3>
            <p className="text-xs text-[#868e96]">
              Simulate price swings to see the exact Rupee impact on your <strong className="text-[#0f1117] font-semibold">{quantity} shares</strong>
            </p>
          </div>
          <div className="text-right">
            <span className="text-xs text-[#868e96]">Simulated Price: </span>
            <strong className="text-sm font-mono text-[#0f1117]">₹{fmt(scenarioPrice)}</strong>
          </div>
        </div>

        {/* Range Slider */}
        <div className="space-y-2 bg-[#f8f9fa] p-4 rounded-xl border border-[#e9ecef]">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="text-[#e03131]">-8.0% (Drop)</span>
            <span className={`text-sm font-mono font-bold px-3 py-0.5 rounded-full ${scenarioChange > 0 ? 'bg-[#ebfbee] text-[#2b8a3e]' : scenarioChange < 0 ? 'bg-[#fff5f5] text-[#e03131]' : 'bg-[#e9ecef] text-[#495057]'}`}>
              {scenarioChange > 0 ? '+' : ''}{scenarioChange.toFixed(1)}% Move
            </span>
            <span className="text-[#2b8a3e]">+8.0% (Rally)</span>
          </div>

          <input
            type="range"
            min={-8}
            max={8}
            step={0.2}
            value={scenarioChange}
            onChange={(e) => setScenarioChange(Number(e.target.value))}
            className="w-full accent-[#1c7ed6] cursor-pointer"
          />

          <div className="flex justify-between text-[10px] text-[#868e96]">
            <span>-8%</span>
            <span className="text-[#e03131]">Stop Loss ({((dynamicStopLoss - entryPrice) / entryPrice * 100).toFixed(1)}%)</span>
            <span>0% (Entry)</span>
            <span className="text-[#2b8a3e]">Target (+{((dynamicTarget - entryPrice) / entryPrice * 100).toFixed(1)}%)</span>
            <span>+8%</span>
          </div>
        </div>

        {/* Scenario Outcome Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-[#f8f9fa] border border-[#e9ecef] rounded-xl p-3">
            <p className="text-[10px] uppercase font-bold text-[#868e96]">Projected Price</p>
            <p className="text-sm font-bold font-mono text-[#0f1117] mt-0.5">₹{fmt(scenarioPrice)}</p>
            <p className="text-[10px] text-[#868e96]">{scenarioChange >= 0 ? '+' : ''}{scenarioChange.toFixed(1)}% from entry</p>
          </div>

          <div className={`border rounded-xl p-3 ${scenarioTotalPnl >= 0 ? 'bg-[#ebfbee] border-[#b2f2bb]' : 'bg-[#fff5f5] border-[#ffc9c9]'}`}>
            <p className={`text-[10px] uppercase font-bold ${scenarioTotalPnl >= 0 ? 'text-[#2b8a3e]' : 'text-[#e03131]'}`}>Total Scenario P/L</p>
            <p className={`text-base font-bold font-mono mt-0.5 ${scenarioTotalPnl >= 0 ? 'text-[#2b8a3e]' : 'text-[#e03131]'}`}>
              {scenarioTotalPnl >= 0 ? '+' : '-'}₹{fmt(Math.abs(scenarioTotalPnl))}
            </p>
            <p className="text-[10px] text-[#868e96]">
              {quantity} sh × {scenarioPnlPerShare >= 0 ? '+' : '-'}₹{fmt(Math.abs(scenarioPnlPerShare))}
            </p>
          </div>

          <div className="bg-[#f8f9fa] border border-[#e9ecef] rounded-xl p-3">
            <p className="text-[10px] uppercase font-bold text-[#868e96]">Stop Loss Status</p>
            <p className={`text-xs font-bold font-mono mt-0.5 ${isScenarioStopHit ? 'text-[#e03131]' : 'text-[#2b8a3e]'}`}>
              {isScenarioStopHit ? '⛔ STOP LOSS HIT' : '✓ Safe Buffer Active'}
            </p>
            <p className="text-[10px] text-[#868e96]">Buffer: ₹{fmt(Math.abs(scenarioPrice - dynamicStopLoss))}</p>
          </div>

          <div className="bg-[#f8f9fa] border border-[#e9ecef] rounded-xl p-3">
            <p className="text-[10px] uppercase font-bold text-[#868e96]">Target Status</p>
            <p className={`text-xs font-bold font-mono mt-0.5 ${isScenarioTargetHit ? 'text-[#2b8a3e]' : 'text-[#495057]'}`}>
              {isScenarioTargetHit ? '🎯 TARGET HIT' : 'Target not reached'}
            </p>
            <p className="text-[10px] text-[#868e96]">Dist: ₹{fmt(Math.abs(dynamicTarget - scenarioPrice))}</p>
          </div>
        </div>
      </div>

      {/* ── 5. TECHNICAL HEALTH CHECKLIST ────────────────────────────────── */}
      <div className="bg-white border border-[#e9ecef] rounded-2xl p-5 shadow-xs">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <h3 className="text-sm font-bold text-[#0f1117] flex items-center gap-1.5">
            <span>🛡️</span> Technical Confluence & Risk Checklist
          </h3>
          <button
            onClick={() => setShowTechnicalDetails(v => !v)}
            className="text-xs text-[#1c7ed6] hover:underline cursor-pointer font-medium"
          >
            {showTechnicalDetails ? '▲ Hide Indicator Details' : '▼ Show Detailed Indicators'}
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="flex items-center gap-2 p-2.5 bg-[#f8f9fa] rounded-xl border border-[#e9ecef]">
            <span className="text-sm">{riskGuardPasses ? '✅' : '⚠️'}</span>
            <div>
              <p className="text-[10px] font-bold text-[#495057]">Risk/Reward Guard</p>
              <p className="text-xs font-semibold text-[#0f1117]">{riskRewardRatio} ({riskGuardPasses ? 'Pass' : 'Moderate'})</p>
            </div>
          </div>

          <div className="flex items-center gap-2 p-2.5 bg-[#f8f9fa] rounded-xl border border-[#e9ecef]">
            <span className="text-sm">{rsi >= 30 && rsi <= 75 ? '✅' : '⚠️'}</span>
            <div>
              <p className="text-[10px] font-bold text-[#495057]">RSI 14 Momentum</p>
              <p className="text-xs font-semibold text-[#0f1117]">{rsi.toFixed(1)} ({rsi > 75 ? 'Overbought' : rsi < 25 ? 'Oversold' : 'Neutral'})</p>
            </div>
          </div>

          <div className="flex items-center gap-2 p-2.5 bg-[#f8f9fa] rounded-xl border border-[#e9ecef]">
            <span className="text-sm">{volumeRatio >= 1.0 ? '✅' : 'ℹ️'}</span>
            <div>
              <p className="text-[10px] font-bold text-[#495057]">Volume Strength</p>
              <p className="text-xs font-semibold text-[#0f1117]">{volumeRatio.toFixed(2)}x ({volumeRatio >= 1.0 ? 'High' : 'Normal'})</p>
            </div>
          </div>

          <div className="flex items-center gap-2 p-2.5 bg-[#f8f9fa] rounded-xl border border-[#e9ecef]">
            <span className="text-sm">{trend.toLowerCase().includes('bull') ? '📈' : '📉'}</span>
            <div>
              <p className="text-[10px] font-bold text-[#495057]">Trend Direction</p>
              <p className="text-xs font-semibold text-[#0f1117]">{trend}</p>
            </div>
          </div>
        </div>

        {showTechnicalDetails && (
          <div className="mt-4 pt-4 border-t border-[#e9ecef] grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="p-2.5 bg-[#f8f9fa] rounded-lg">
              <span className="text-[#868e96] block text-[10px]">14-Period ATR</span>
              <strong className="font-mono text-[#0f1117]">₹{atr.toFixed(2)} points</strong>
            </div>
            <div className="p-2.5 bg-[#f8f9fa] rounded-lg">
              <span className="text-[#868e96] block text-[10px]">Optimal Entry Zone</span>
              <strong className="font-mono text-[#1c7ed6]">{entryZone}</strong>
            </div>
            <div className="p-2.5 bg-[#f8f9fa] rounded-lg">
              <span className="text-[#868e96] block text-[10px]">20-Day Volatility</span>
              <strong className="font-mono text-[#0f1117]">{prediction?.analytics?.volatility_20_pct ?? 14.6}%</strong>
            </div>
            <div className="p-2.5 bg-[#f8f9fa] rounded-lg">
              <span className="text-[#868e96] block text-[10px]">AI Trade Score</span>
              <strong className="font-mono text-[#2b8a3e]">{prediction?.analytics?.trade_score ?? 82}/100</strong>
            </div>
          </div>
        )}
      </div>

      {/* ── 6. ORDER EXECUTION & REGISTRATION BAR ────────────────────────── */}
      <div className="bg-white border border-[#e9ecef] rounded-2xl p-5 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${executedTrade ? 'bg-[#2b8a3e] animate-ping' : 'bg-[#1971c2]'}`} />
              <h3 className="text-base font-bold text-[#0f1117]">Execute & Record Order</h3>
              <span className="text-xs font-bold px-2.5 py-0.5 bg-[#f1f3f5] text-[#495057] font-mono rounded">
                {selectedCompany.ticker} · {signalType === 'SELL' ? 'SELL' : 'BUY'} {quantity} shares @ ₹{fmt(entryPrice)}
              </span>
            </div>
            <p className="text-xs text-[#868e96] mt-1">
              {executedTrade
                ? 'Order registered successfully! Position is now monitored with live Stop Loss & Target in your Profile ledger.'
                : `Clicking below records this order (₹${fmt(requiredCapital)} capital, Stop Loss ₹${fmt(dynamicStopLoss)}, Target ₹${fmt(dynamicTarget)}) directly into your Trade History.`}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {executedTrade ? (
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[#2b8a3e] bg-[#ebfbee] border border-[#b2f2bb] px-3.5 py-2.5 rounded-xl">
                  ✓ Recorded ({executedTrade.ticker})
                </span>
                <button
                  type="button"
                  onClick={() => onNavigate('profile')}
                  className="px-4 py-2.5 text-xs font-bold text-white bg-[#1971c2] hover:bg-[#1864ab] rounded-xl transition-colors flex items-center gap-1 cursor-pointer shadow-sm"
                >
                  View in Profile →
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleExecuteTrade}
                disabled={isExecuting || loading}
                className={`px-6 py-3 text-xs font-bold text-white rounded-xl transition-all flex items-center gap-2 cursor-pointer shadow-md disabled:opacity-50 ${signalType === 'SELL' ? 'bg-[#e03131] hover:bg-[#c92a2a]' : 'bg-[#2b8a3e] hover:bg-[#237032]'}`}
              >
                {isExecuting ? (
                  <>
                    <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                    </svg>
                    <span>Executing Trade...</span>
                  </>
                ) : (
                  <>
                    <span>⚡ EXECUTE {signalType === 'SELL' ? 'SELL' : 'BUY'} ({quantity} SHARES)</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {executionError && (
          <div className="mt-3 p-3 bg-[#fff5f5] text-[#e03131] border border-[#ffc9c9] rounded-xl text-xs flex items-center justify-between">
            <span>{executionError}</span>
            <button type="button" onClick={() => setExecutionError(null)} className="text-[#e03131] font-bold text-xs hover:underline ml-2 cursor-pointer">Dismiss</button>
          </div>
        )}
      </div>

    </div>
  )
}
