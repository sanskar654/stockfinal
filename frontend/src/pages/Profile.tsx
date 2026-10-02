import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '../context/AuthContext'
import {
  getUserProfile,
  updateUserProfile,
  closeUserTrade,
} from '../lib/api'
import type {
  ProfileResponse,
  TradeHistoryItem,
} from '../types/api'

function fmt(n: number) {
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n)
}

function fmtShort(n: number) {
  if (Math.abs(n) >= 100000) return `₹${(n / 100000).toFixed(1)}L`
  if (Math.abs(n) >= 1000) return `₹${(n / 1000).toFixed(1)}K`
  return `₹${fmt(n)}`
}

/** Compute win rate only from trades that have a non-null PnL (closed positions) */
function computeStats(trades: TradeHistoryItem[]) {
  const closedTrades = trades.filter(t => t.pnl !== null && t.pnl !== undefined)
  const winningTrades = closedTrades.filter(t => (t.pnl ?? 0) > 0)
  const losingTrades = closedTrades.filter(t => (t.pnl ?? 0) < 0)
  const totalPnl = closedTrades.reduce((sum, t) => sum + (Number(t.pnl) || 0), 0)
  const winRate = closedTrades.length > 0 ? (winningTrades.length / closedTrades.length) * 100 : 0
  const avgWin = winningTrades.length > 0
    ? winningTrades.reduce((s, t) => s + (Number(t.pnl) || 0), 0) / winningTrades.length
    : 0
  const avgLoss = losingTrades.length > 0
    ? losingTrades.reduce((s, t) => s + (Number(t.pnl) || 0), 0) / losingTrades.length
    : 0
  return { closedTrades, winningTrades, losingTrades, totalPnl, winRate, avgWin, avgLoss }
}

export default function Profile() {
  const { currentUser, logout } = useAuth()

  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [isEditing, setIsEditing] = useState<boolean>(false)
  const [saving, setSaving] = useState<boolean>(false)
  const [feedback, setFeedback] = useState<string | null>(null)

  // Close trade modal state
  const [closingTrade, setClosingTrade] = useState<TradeHistoryItem | null>(null)
  const [exitPrice, setExitPrice] = useState<string>('')
  const [closingLoading, setClosingLoading] = useState<boolean>(false)

  // Edit form state
  const [editForm, setEditForm] = useState({
    fullName: '',
    email: '',
    username: '',
    phone: '',
  })

  const loadProfileData = async () => {
    try {
      setLoading(true)
      const activeId = currentUser?.id || 'usr_demo_trader'
      const userMeta = currentUser ? {
        fullName: currentUser.fullName,
        email: currentUser.email,
        username: currentUser.username,
        phone: currentUser.phone,
        avatarInitials: currentUser.avatarInitials,
      } : undefined

      const profData = await getUserProfile(activeId, userMeta)
      setProfile(profData)
      setEditForm({
        fullName: profData.full_name,
        email: profData.email,
        username: profData.username,
        phone: profData.phone,
      })
    } catch (err) {
      console.error('Failed to load profile data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProfileData()
  }, [currentUser?.id])

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setFeedback(null)
    try {
      const activeId = profile?.id || currentUser?.id || 'usr_demo_trader'
      const updated = await updateUserProfile(
        {
          full_name: editForm.fullName,
          email: editForm.email,
          username: editForm.username,
          phone: editForm.phone,
        },
        activeId,
      )
      setProfile(updated)
      setIsEditing(false)
      setFeedback('Profile updated successfully!')
      setTimeout(() => setFeedback(null), 4000)
    } catch (err: any) {
      setFeedback(`Failed to update profile: ${err.message || err}`)
    } finally {
      setSaving(false)
    }
  }

  const handleOpenCloseModal = (trade: TradeHistoryItem) => {
    setClosingTrade(trade)
    setExitPrice(String(trade.price))
  }

  const handleConfirmClose = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!closingTrade) return
    const numericExit = parseFloat(exitPrice)
    if (isNaN(numericExit) || numericExit <= 0) {
      setFeedback('Please enter a valid positive exit price.')
      return
    }
    setClosingLoading(true)
    setFeedback(null)
    try {
      await closeUserTrade(closingTrade.id, numericExit)
      setClosingTrade(null)
      setFeedback(`Trade on ${closingTrade.ticker} closed successfully!`)
      await loadProfileData()
      setTimeout(() => setFeedback(null), 4000)
    } catch (err: any) {
      setFeedback(`Failed to close trade: ${err.message || err}`)
    } finally {
      setClosingLoading(false)
    }
  }

  const isDemo = !currentUser || currentUser.id === 'usr_demo_trader'

  // Display fallbacks
  const displayName = profile?.full_name || currentUser?.fullName || (isDemo ? 'John Doe' : 'Trader')
  const displayEmail = profile?.email || currentUser?.email || (isDemo ? 'demo@virtuebyte.com' : '')
  const displayUsername = profile?.username
    ? `@${profile.username}`
    : (currentUser?.username ? `@${currentUser.username}` : (isDemo ? '@johndoe' : ''))
  const displayPhone = profile?.phone
    ? (profile.phone.startsWith('+') ? profile.phone : `+91 ${profile.phone}`)
    : (currentUser?.phone ? `+91 ${currentUser.phone}` : (isDemo ? '+91 9876543210' : ''))
  const initials = profile?.avatar_initials || currentUser?.avatarInitials || (isDemo ? 'JD' : 'TR')
  const memberSince = profile?.registered_at
    ? new Date(profile.registered_at).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
    : (isDemo ? 'Jan 2026' : 'Today')

  // Sort trades newest-first
  const trades: TradeHistoryItem[] = [...(profile?.recent_trades ?? [])].sort((a, b) => {
    const left = a.created_at || a.date || ''
    const right = b.created_at || b.date || ''
    return right.localeCompare(left)
  })

  // Compute stats from actual trade records (not backend zeros)
  const { closedTrades, winningTrades, losingTrades, totalPnl, winRate, avgWin, avgLoss } = computeStats(trades)
  const openTrades = trades.filter(t => t.pnl === null || t.pnl === undefined)

  // Demo user shows demo stats; real account uses computed stats from trades
  const totalTrades = trades.length > 0 ? trades.length : (isDemo ? 5 : 0)
  const displayWinRate = trades.length > 0 ? winRate : (isDemo ? 66.7 : 0)
  const displayPnl = trades.length > 0 ? totalPnl : (isDemo ? 1337.0 : 0)

  const groupedTrades = trades.reduce<Record<string, TradeHistoryItem[]>>((acc, trade) => {
    const key = trade.date || new Date(trade.created_at || Date.now()).toISOString().slice(0, 10)
    acc[key] = acc[key] || []
    acc[key].push(trade)
    return acc
  }, {})
  const orderedDates = Object.keys(groupedTrades).sort((a, b) => b.localeCompare(a))

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-[#0f1117]">User Profile</h1>
          <p className="text-sm text-[#868e96] mt-0.5">Trading account overview &amp; history</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsEditing(true)}
            className="px-3 py-1.5 text-xs font-semibold text-[#1971c2] hover:text-white hover:bg-[#1971c2] border border-[#a5d8ff] rounded transition-colors"
          >
            Edit Profile
          </button>
          {currentUser && (
            <button
              onClick={logout}
              className="px-3 py-1.5 text-xs font-semibold text-[#e03131] hover:text-white hover:bg-[#e03131] border border-[#ffc9c9] rounded transition-colors"
            >
              Sign Out
            </button>
          )}
        </div>
      </div>

      {/* Feedback banner */}
      {feedback && (
        <div className={`p-3 text-xs font-medium rounded border ${
          feedback.includes('Failed') ? 'bg-[#fff5f5] text-[#e03131] border-[#ffc9c9]' : 'bg-[#ebfbee] text-[#2f9e44] border-[#b2f2bb]'
        }`}>
          {feedback}
        </div>
      )}

      {/* User Info Card */}
      <div className="bg-white border border-[#e9ecef] rounded-xl p-6 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center gap-6">
          <div className="w-16 h-16 bg-gradient-to-br from-[#1c7ed6] to-[#0f1117] rounded-full flex items-center justify-center shrink-0 shadow-sm">
            <span className="text-white text-xl font-bold tracking-tight">{initials}</span>
          </div>
          <div className="space-y-1 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-semibold text-[#0f1117]">{displayName}</h2>
              <span className="text-[10px] px-2 py-0.5 bg-[#ebfbee] text-[#2f9e44] font-medium rounded">
                Verified Trader
              </span>
              {isDemo && (
                <span className="text-[10px] px-2 py-0.5 bg-[#fff3bf] text-[#b7791f] font-medium rounded">
                  Demo Mode
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#868e96]">
              <span>{displayEmail}</span>
              <span>•</span>
              <span>{displayUsername}</span>
              <span>•</span>
              <span>{displayPhone}</span>
              <span>•</span>
              <span>Member since {memberSince}</span>
            </div>
          </div>

          <div className="flex gap-6 text-center shrink-0">
            <div>
              <p className="text-[10px] text-[#868e96] uppercase tracking-widest font-medium">Total Trades</p>
              <p className="text-lg font-bold text-[#0f1117] mt-1">{totalTrades}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Stats Grid — computed from actual trades */}
      <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
        <StatCard
          label="Total Trades"
          value={String(totalTrades)}
          sub={`${openTrades.length} open • ${closedTrades.length} closed`}
        />
        <StatCard
          label="Win Rate"
          value={closedTrades.length > 0 ? `${displayWinRate.toFixed(1)}%` : (isDemo ? '66.7%' : '—')}
          sub={closedTrades.length > 0
            ? `${winningTrades.length}W / ${losingTrades.length}L`
            : closedTrades.length === 0 && openTrades.length > 0
              ? 'Positions open'
              : isDemo ? '3W / 2L' : 'No closed trades yet'}
          colored={displayWinRate > 50 ? 'green' : displayWinRate > 0 ? 'red' : undefined}
        />
        <StatCard
          label="Realized P&L"
          value={closedTrades.length > 0 ? fmtShort(displayPnl) : (isDemo ? '₹1,337.00' : '—')}
          sub={closedTrades.length > 0
            ? displayPnl >= 0 ? 'Net profit' : 'Net loss'
            : openTrades.length > 0 ? 'Awaiting close' : isDemo ? 'Net profit' : 'No closed trades'}
          colored={displayPnl > 0 ? 'green' : displayPnl < 0 ? 'red' : undefined}
        />
        <StatCard
          label="Avg Win / Loss"
          value={closedTrades.length > 0
            ? `${fmtShort(avgWin)} / ${fmtShort(Math.abs(avgLoss))}`
            : (isDemo ? '₹450 / ₹180' : '—')}
          sub={closedTrades.length > 0
            ? avgWin > 0 && avgLoss < 0
              ? `RR Ratio: ${Math.abs(avgWin / avgLoss).toFixed(2)}`
              : 'Track record'
            : 'No closed trades yet'}
          colored={avgWin > Math.abs(avgLoss) ? 'green' : undefined}
        />
      </div>

      {/* Trade History */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-[#0f1117]">
            {isDemo ? 'Demo Trade History' : 'Your Trade History'}
          </h2>
          <div className="flex items-center gap-3">
            {openTrades.length > 0 && (
              <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-[#1971c2] bg-[#e7f5ff] border border-[#a5d8ff] px-2.5 py-1 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-[#1c7ed6] animate-pulse" />
                {openTrades.length} Open Position{openTrades.length > 1 ? 's' : ''}
              </span>
            )}
            <span className="text-xs text-[#868e96]">{trades.length} recorded trade{trades.length === 1 ? '' : 's'}</span>
          </div>
        </div>

        {trades.length === 0 ? (
          <div className="bg-white border border-[#e9ecef] rounded-xl p-10 text-center shadow-xs">
            <div className="w-12 h-12 bg-[#f1f3f5] rounded-full flex items-center justify-center mx-auto mb-3">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#adb5bd" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 3v18h18" /><path d="m19 9-5 5-4-4-3 3" />
              </svg>
            </div>
            <p className="text-sm font-medium text-[#495057]">No trades recorded yet</p>
            <p className="text-xs text-[#868e96] mt-1">Execute a trade from the Risk Management tab to see it here.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {orderedDates.map((date) => {
              const dayTrades = groupedTrades[date] || []
              const dayClosedTrades = dayTrades.filter(t => t.pnl !== null && t.pnl !== undefined)
              const dayPnl = dayClosedTrades.reduce((sum, trade) => sum + (Number(trade.pnl) || 0), 0)
              const dayOpenCount = dayTrades.filter(t => t.pnl === null || t.pnl === undefined).length
              return (
                <div key={date} className="bg-white border border-[#e9ecef] rounded-xl overflow-hidden shadow-xs">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-[#e9ecef] bg-[#f8f9fa]">
                    <div>
                      <p className="text-xs font-semibold text-[#0f1117]">{new Date(`${date}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</p>
                      <p className="text-[10px] text-[#868e96] mt-0.5">{dayTrades.length} trade{dayTrades.length > 1 ? 's' : ''}{dayOpenCount > 0 ? ` • ${dayOpenCount} open` : ''}</p>
                    </div>
                    <div className="text-right">
                      {dayClosedTrades.length > 0 ? (
                        <>
                          <p className="text-[10px] uppercase tracking-[0.18em] text-[#868e96]">Day P&amp;L</p>
                          <p className={`text-sm font-semibold ${dayPnl >= 0 ? 'text-[#2f9e44]' : 'text-[#e03131]'}`}>
                            {dayPnl >= 0 ? '+' : ''}₹{fmt(dayPnl)}
                          </p>
                        </>
                      ) : (
                        <span className="text-[10px] text-[#adb5bd] italic">Open positions</span>
                      )}
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm whitespace-nowrap">
                      <thead className="bg-white border-b border-[#e9ecef]">
                        <tr>
                          <th className="px-4 py-3 font-medium text-[#495057]">Ticker</th>
                          <th className="px-4 py-3 font-medium text-[#495057]">Type</th>
                          <th className="px-4 py-3 font-medium text-[#495057]">Qty</th>
                          <th className="px-4 py-3 font-medium text-[#495057]">Price</th>
                          <th className="px-4 py-3 font-medium text-[#495057]">P&amp;L</th>
                          <th className="px-4 py-3 font-medium text-[#495057]">Status</th>
                          <th className="px-4 py-3 font-medium text-[#495057] text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#e9ecef]">
                        {dayTrades.map((trade, idx) => {
                          const hasPnl = trade.pnl !== null && trade.pnl !== undefined
                          const pnlValue = Number(trade.pnl || 0)
                          return (
                            <tr key={`${trade.ticker}-${trade.date}-${trade.created_at || idx}`} className="hover:bg-[#f8f9fa] transition-colors">
                              <td className="px-4 py-3 font-medium text-[#0f1117]">
                                <span className="font-mono">{trade.ticker}</span>
                              </td>
                              <td className="px-4 py-3">
                                <span className={`inline-block px-2 py-0.5 text-[10px] font-bold rounded ${
                                  trade.type === 'BUY' ? 'bg-[#ebfbee] text-[#2f9e44]' : 'bg-[#fff5f5] text-[#e03131]'
                                }`}>
                                  {trade.type}
                                </span>
                              </td>
                              <td className="px-4 py-3 font-mono text-xs text-[#0f1117]">{trade.qty}</td>
                              <td className="px-4 py-3 font-mono text-xs text-[#0f1117]">₹{fmt(trade.price)}</td>
                              <td className={`px-4 py-3 font-mono text-xs font-semibold ${
                                !hasPnl ? 'text-[#adb5bd]' :
                                pnlValue >= 0 ? 'text-[#2f9e44]' : 'text-[#e03131]'
                              }`}>
                                {!hasPnl ? (
                                  <span className="inline-flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-[#1c7ed6] animate-pulse" />
                                    Open
                                  </span>
                                ) : (
                                  `${pnlValue >= 0 ? '+' : ''}₹${fmt(pnlValue)}`
                                )}
                              </td>
                              <td className="px-4 py-3 text-[#495057] text-xs">
                                {hasPnl ? (
                                  <span className={`inline-block px-2 py-0.5 text-[10px] font-semibold rounded ${
                                    pnlValue >= 0 ? 'bg-[#ebfbee] text-[#2f9e44]' : 'bg-[#fff5f5] text-[#e03131]'
                                  }`}>
                                    {trade.status || 'CLOSED'}
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#1971c2] bg-[#e7f5ff] px-2 py-0.5 rounded">
                                    ACTIVE
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-right">
                                {!hasPnl ? (
                                  <button
                                    onClick={() => handleOpenCloseModal(trade)}
                                    className="px-2.5 py-1 text-[11px] font-semibold text-[#c92a2a] bg-[#fff5f5] hover:bg-[#ffe3e3] border border-[#ffc9c9] rounded transition-colors cursor-pointer"
                                    title="Exit this position and realize P&L"
                                  >
                                    Close Position
                                  </button>
                                ) : (
                                  <span className="text-[11px] text-[#adb5bd] font-mono">Settled</span>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Close Position Modal */}
      {closingTrade && createPortal(
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs transition-all"
          onClick={(e) => { if (e.target === e.currentTarget) setClosingTrade(null) }}
        >
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-2xl border border-[#e9ecef] relative animate-in fade-in zoom-in-95 duration-150">
            <h3 className="text-base font-bold text-[#0f1117] mb-1">Close Position — {closingTrade.ticker}</h3>
            <p className="text-xs text-[#868e96] mb-4">
              Enter your exit price to realize the profit or loss on this trade.
            </p>

            <form onSubmit={handleConfirmClose} className="space-y-4 text-xs">
              <div className="bg-[#f8f9fa] border border-[#e9ecef] rounded-lg p-3 space-y-1.5 font-mono">
                <div className="flex justify-between text-xs">
                  <span className="text-[#868e96]">Side / Quantity:</span>
                  <span className="font-semibold text-[#0f1117]">{closingTrade.type} {closingTrade.qty} units</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-[#868e96]">Entry Price:</span>
                  <span className="font-semibold text-[#0f1117]">₹{fmt(closingTrade.price)}</span>
                </div>
                <div className="flex justify-between text-xs pt-1.5 border-t border-[#e9ecef]">
                  <span className="text-[#868e96]">Est. Realized P&amp;L:</span>
                  {(() => {
                    const exit = parseFloat(exitPrice) || 0
                    const pnlEst = closingTrade.type === 'BUY'
                      ? (exit - closingTrade.price) * closingTrade.qty
                      : (closingTrade.price - exit) * closingTrade.qty
                    return (
                      <span className={`font-bold ${pnlEst >= 0 ? 'text-[#2f9e44]' : 'text-[#e03131]'}`}>
                        {pnlEst >= 0 ? '+' : ''}₹{fmt(pnlEst)}
                      </span>
                    )
                  })()}
                </div>
              </div>

              <div>
                <label className="block font-medium text-[#495057] mb-1">Exit Price (₹)</label>
                <input
                  type="number"
                  step="0.05"
                  value={exitPrice}
                  onChange={e => setExitPrice(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-[#ced4da] rounded focus:outline-hidden focus:border-[#1971c2] font-mono text-sm"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setClosingTrade(null)}
                  className="px-3 py-1.5 text-xs text-[#495057] hover:bg-[#f1f3f5] rounded border border-[#ced4da] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={closingLoading}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-[#c92a2a] hover:bg-[#b02525] rounded transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {closingLoading ? 'Closing...' : 'Confirm Exit'}
                </button>
              </div>
            </form>
          </div>
        </div>,
        document.body
      )}

      {/* Edit Profile Modal */}
      {isEditing && createPortal(
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs transition-all"
          onClick={(e) => { if (e.target === e.currentTarget) setIsEditing(false) }}
        >
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-2xl border border-[#e9ecef] relative animate-in fade-in zoom-in-95 duration-150">
            <h3 className="text-base font-bold text-[#0f1117] mb-1">Edit Profile Details</h3>
            <p className="text-xs text-[#868e96] mb-4">Updates will be saved directly into the local SQLite profile database.</p>

            <form onSubmit={handleSaveProfile} className="space-y-3 text-xs">
              <div>
                <label className="block font-medium text-[#495057] mb-1">Full Name</label>
                <input
                  type="text"
                  value={editForm.fullName}
                  onChange={e => setEditForm(f => ({ ...f, fullName: e.target.value }))}
                  required
                  className="w-full px-3 py-2 border border-[#ced4da] rounded focus:outline-hidden focus:border-[#1971c2]"
                />
              </div>
              <div>
                <label className="block font-medium text-[#495057] mb-1">Email</label>
                <input
                  type="email"
                  value={editForm.email}
                  onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))}
                  required
                  className="w-full px-3 py-2 border border-[#ced4da] rounded focus:outline-hidden focus:border-[#1971c2]"
                />
              </div>
              <div>
                <label className="block font-medium text-[#495057] mb-1">Username</label>
                <input
                  type="text"
                  value={editForm.username}
                  onChange={e => setEditForm(f => ({ ...f, username: e.target.value }))}
                  required
                  className="w-full px-3 py-2 border border-[#ced4da] rounded focus:outline-hidden focus:border-[#1971c2]"
                />
              </div>
              <div>
                <label className="block font-medium text-[#495057] mb-1">Phone</label>
                <input
                  type="tel"
                  value={editForm.phone}
                  onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))}
                  required
                  className="w-full px-3 py-2 border border-[#ced4da] rounded focus:outline-hidden focus:border-[#1971c2]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-[#e9ecef]">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="px-3 py-1.5 font-semibold text-[#495057] hover:bg-[#f1f3f5] rounded border border-[#ced4da] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-1.5 font-semibold text-white bg-[#1971c2] hover:bg-[#1864ab] rounded transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

function StatCard({ label, value, sub, colored }: {
  label: string
  value: string
  sub?: string
  colored?: 'green' | 'red'
}) {
  return (
    <div className="bg-white border border-[#e9ecef] rounded-xl p-4 shadow-xs">
      <p className="text-[10px] uppercase tracking-[0.18em] text-[#868e96]">{label}</p>
      <p className={`mt-2 text-xl font-bold font-mono ${
        colored === 'green' ? 'text-[#2f9e44]' :
        colored === 'red' ? 'text-[#e03131]' :
        'text-[#0f1117]'
      }`}>{value}</p>
      {sub && <p className="text-[10px] text-[#adb5bd] mt-1">{sub}</p>}
    </div>
  )
}
