// Navigation configuration for CryptoTrader sidebar

export const VIEW_IDS = {
  // Trading
  DASHBOARD: 'dashboard',
  CHART: 'chart',
  ORDERS: 'orders',
  POSITIONS: 'positions',
  // Analysis
  SIGNALS: 'signals',
  OPPORTUNITIES: 'opportunities',
  // Market Data
  MARKET_WATCH: 'market-watch',
  INGESTION_STATUS: 'ingestion-status',
  // Account
  WALLET: 'wallet',
  SETTINGS: 'settings',
  // System
  SYSTEM_STATUS: 'system-status',
} as const

export type ViewId = (typeof VIEW_IDS)[keyof typeof VIEW_IDS]

export interface NavItem {
  id: ViewId
  label: string
  icon: string
  status?: 'ready' | 'new' | 'beta'
}

export interface NavGroup {
  id: string
  title: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'trading',
    title: 'Trading',
    items: [
      { id: VIEW_IDS.DASHBOARD, label: 'Dashboard', icon: '📊', status: 'ready' },
      { id: VIEW_IDS.CHART, label: 'Chart', icon: '📈', status: 'ready' },
      { id: VIEW_IDS.ORDERS, label: 'Orders', icon: '📝', status: 'ready' },
      { id: VIEW_IDS.POSITIONS, label: 'Positions', icon: '💼', status: 'ready' },
    ],
  },
  {
    id: 'analysis',
    title: 'Analysis',
    items: [
      { id: VIEW_IDS.SIGNALS, label: 'Signals', icon: '🎯', status: 'ready' },
      { id: VIEW_IDS.OPPORTUNITIES, label: 'Opportunities', icon: '💡', status: 'beta' },
    ],
  },
  {
    id: 'market-data',
    title: 'Market Data',
    items: [
      { id: VIEW_IDS.MARKET_WATCH, label: 'Market Watch', icon: '👁️', status: 'ready' },
      { id: VIEW_IDS.INGESTION_STATUS, label: 'Ingestion', icon: '📥', status: 'ready' },
    ],
  },
  {
    id: 'account',
    title: 'Account',
    items: [
      { id: VIEW_IDS.WALLET, label: 'Wallet', icon: '💰', status: 'ready' },
      { id: VIEW_IDS.SETTINGS, label: 'Settings', icon: '⚙️', status: 'ready' },
    ],
  },
  {
    id: 'system',
    title: 'System',
    items: [
      { id: VIEW_IDS.SYSTEM_STATUS, label: 'Status', icon: '🔧', status: 'ready' },
    ],
  },
]
