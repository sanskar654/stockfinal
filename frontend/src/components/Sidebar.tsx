import type { Page } from '../App'
import { useAuth } from '../context/AuthContext'

interface SidebarProps {
  currentPage: Page
  onNavigate: (page: Page) => void
  open: boolean
  onNavigateToAuth?: () => void
}

const navItems: { id: Page; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'trade-discovery', label: 'Trade Discovery' },
  { id: 'risk-management', label: 'Risk Management' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'profile', label: 'Profile' },
]

const modelStatus = {
  api: 'Connected',
}

export default function Sidebar({ currentPage, onNavigate, open, onNavigateToAuth }: SidebarProps) {
  const { currentUser, logout, isAuthenticated } = useAuth()

  return (
    <aside
      className={`
        h-full shrink-0 overflow-hidden flex flex-col bg-white border-r border-[#e9ecef]
        transition-all duration-200 ease-in-out shadow-[0_0_0_1px_rgba(15,17,23,0.02)]
        ${open ? 'w-56 opacity-100' : 'w-0 opacity-0 border-r-0'}
      `}
    >
      <div className={`px-4 py-5 border-b border-[#e9ecef] bg-[#f8fafc] transition-opacity duration-200 ${open ? 'opacity-100' : 'opacity-0'}`}>
        <div className="flex items-center gap-2 mb-0.5">
          <div className="w-7 h-7 bg-[#0f1117] rounded-lg flex items-center justify-center shadow-sm">
            <span className="text-white text-[10px] font-bold tracking-tight">N5</span>
          </div>
          <div>
            <span className="text-sm font-bold text-[#0f1117] tracking-tight">NIFTY50-ML</span>
            <p className="text-[10px] text-[#868e96] tracking-[0.12em] uppercase">Trading Intelligence</p>
          </div>
        </div>
      </div>

      <nav className={`flex-1 py-3 px-2 space-y-1 transition-opacity duration-200 ${open ? 'opacity-100' : 'opacity-0'}`}>
        {navItems.map(item => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className={`
              w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left text-sm transition-all
              ${currentPage === item.id
                ? 'bg-[#0f1117] text-white font-medium shadow-sm'
                : 'text-[#495057] hover:bg-[#f1f3f5] hover:text-[#0f1117]'
              }
            `}
          >
            <span className={`h-2 w-2 rounded-full ${currentPage === item.id ? 'bg-[#1c7ed6]' : 'bg-[#adb5bd]'}`} />
            {item.label}
          </button>
        ))}
      </nav>

      <div className={`p-3 border-t border-[#e9ecef] space-y-3 transition-opacity duration-200 ${open ? 'opacity-100' : 'opacity-0'}`}>
        {isAuthenticated && currentUser ? (
          <div className="bg-[#f8f9fa] border border-[#e9ecef] rounded-xl p-2.5">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-7 h-7 bg-[#0f1117] text-white rounded-full flex items-center justify-center text-xs font-semibold shrink-0">
                {currentUser.avatarInitials}
              </div>
              <div className="overflow-hidden">
                <p className="text-xs font-semibold text-[#0f1117] truncate leading-tight">{currentUser.fullName}</p>
                <p className="text-[10px] text-[#868e96] truncate">@{currentUser.username}</p>
              </div>
            </div>
            <div className="flex gap-1">
              <button
                onClick={() => onNavigate('profile')}
                className="flex-1 py-1.5 text-[11px] font-medium text-[#495057] hover:text-[#0f1117] bg-white border border-[#e9ecef] rounded-lg hover:bg-[#f1f3f5] transition-colors text-center"
              >
                Profile
              </button>
              <button
                onClick={logout}
                className="flex-1 py-1.5 text-[11px] font-medium text-[#e03131] hover:text-[#c92a2a] bg-white border border-[#e9ecef] rounded-lg hover:bg-[#fff5f5] transition-colors text-center"
              >
                Log Out
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={onNavigateToAuth}
            className="w-full py-2.5 bg-[#0f1117] text-white text-xs font-semibold rounded-xl hover:bg-[#212529] transition-colors shadow-sm"
          >
            Sign In / Register
          </button>
        )}

        <div className="flex items-center justify-between pt-1">
          <span className="text-[10px] text-[#868e96]">API Status</span>
          <span className="flex items-center gap-1 text-[10px] text-[#2f9e44] font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-[#2f9e44] inline-block animate-pulse" />
            {modelStatus.api}
          </span>
        </div>
      </div>
    </aside>
  )
}

