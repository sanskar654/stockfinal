/**
 * Market Status Utility — Indian Stock Exchange (NSE) timing.
 *
 * Market hours (IST):
 *   Pre-market:  09:00 – 09:15
 *   Open:        09:15 – 15:30
 *   Closed:      All other times, weekends, and NSE holidays
 *
 * Predictions continue to work regardless of status (for testing).
 */

export type MarketStatus = 'open' | 'pre-market' | 'closed'

/** Major NSE holidays for 2024-2026 (MM-DD format). Extend as needed. */
const NSE_HOLIDAYS: Set<string> = new Set([
  // 2024
  '01-26', '03-08', '03-25', '03-29', '04-11', '04-14', '04-17', '04-21',
  '05-01', '05-23', '06-17', '07-17', '08-15', '09-16', '10-02', '10-12',
  '10-31', '11-01', '11-15', '12-25',
  // 2025
  '01-26', '02-26', '03-14', '03-31', '04-10', '04-14', '04-18',
  '05-01', '05-12', '06-26', '07-06', '08-15', '08-16', '08-27',
  '10-02', '10-20', '10-21', '10-22', '11-05', '11-26', '12-25',
  // 2026
  '01-26', '02-17', '03-10', '03-19', '03-30', '04-03', '04-14',
  '05-01', '05-25', '07-17', '08-15', '08-28', '10-02', '10-08',
  '10-19', '10-25', '11-24', '12-25',
])

/** Get current IST Date parts */
function getISTNow(): { hours: number; minutes: number; day: number; monthDay: string; isWeekend: boolean } {
  const now = new Date()
  // Convert to IST (UTC+5:30)
  const istOffsetMs = 5.5 * 60 * 60 * 1000
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60 * 1000
  const istDate = new Date(utcMs + istOffsetMs)

  const hours = istDate.getHours()
  const minutes = istDate.getMinutes()
  const day = istDate.getDay() // 0=Sun, 6=Sat
  const month = String(istDate.getMonth() + 1).padStart(2, '0')
  const date = String(istDate.getDate()).padStart(2, '0')

  return {
    hours,
    minutes,
    day,
    monthDay: `${month}-${date}`,
    isWeekend: day === 0 || day === 6,
  }
}

/** Get the current market status */
export function getMarketStatus(): MarketStatus {
  const { hours, minutes, isWeekend, monthDay } = getISTNow()

  // Weekends
  if (isWeekend) return 'closed'

  // NSE holidays
  if (NSE_HOLIDAYS.has(monthDay)) return 'closed'

  const timeInMinutes = hours * 60 + minutes

  // Pre-market: 9:00 - 9:15 IST
  if (timeInMinutes >= 540 && timeInMinutes < 555) return 'pre-market'

  // Market open: 9:15 - 15:30 IST
  if (timeInMinutes >= 555 && timeInMinutes < 930) return 'open'

  return 'closed'
}

/** Human-readable label for the status */
export function getMarketStatusLabel(status: MarketStatus): string {
  switch (status) {
    case 'open':
      return 'Market Open'
    case 'pre-market':
      return 'Pre-Market'
    case 'closed':
      return 'Market Closed'
  }
}

/** Status color for UI */
export function getMarketStatusColor(status: MarketStatus): { bg: string; text: string; dot: string } {
  switch (status) {
    case 'open':
      return { bg: 'bg-[#ebfbee]', text: 'text-[#2f9e44]', dot: 'bg-[#2f9e44]' }
    case 'pre-market':
      return { bg: 'bg-[#fff9db]', text: 'text-[#e67700]', dot: 'bg-[#f59f00]' }
    case 'closed':
      return { bg: 'bg-[#fff5f5]', text: 'text-[#e03131]', dot: 'bg-[#e03131]' }
  }
}

/** Get a human-readable reason why the market is closed */
export function getClosedReason(): string {
  const { isWeekend, monthDay, hours, minutes } = getISTNow()

  if (isWeekend) return 'The market is closed on weekends.'
  if (NSE_HOLIDAYS.has(monthDay)) return 'The market is closed today for an NSE holiday.'

  const timeInMinutes = hours * 60 + minutes
  if (timeInMinutes < 540) return "The market hasn't opened yet. Trading starts at 9:15 AM IST."
  if (timeInMinutes >= 930) return 'The market closed at 3:30 PM IST. Trading resumes tomorrow at 9:15 AM IST.'

  return 'The market is currently closed.'
}
