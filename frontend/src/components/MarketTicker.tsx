import { NIFTY50_COMPANIES } from '../App'

function formatPrice(price: number) {
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(price)
}

export default function MarketTicker() {
  const tape = [...NIFTY50_COMPANIES, ...NIFTY50_COMPANIES]

  return (
    <div className="market-ticker" aria-label="NIFTY 50 market ticker">
      <div className="market-ticker__lead">
        <span className="market-ticker__pulse" />
        <span>MARKET TAPE</span>
      </div>
      <div className="market-ticker__viewport">
        <div className="market-ticker__track">
          {tape.map((company, index) => {
            const positive = company.changePct >= 0
            return (
              <span className="market-ticker__item" key={`${company.ticker}-${index}`}>
                <strong>{company.ticker}</strong>
                <span className="font-mono">₹{formatPrice(company.price)}</span>
                <span className={positive ? 'market-ticker__up' : 'market-ticker__down'}>
                  {positive ? '+' : ''}{company.changePct.toFixed(2)}%
                </span>
              </span>
            )
          })}
        </div>
      </div>
      <span className="market-ticker__session">NSE · 15 MIN GUIDANCE</span>
    </div>
  )
}