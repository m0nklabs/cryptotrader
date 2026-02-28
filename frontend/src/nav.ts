// Navigation configuration for CryptoTrader sidebar

export const VIEW_IDS = {
  // Trading
  DASHBOARD: 'dashboard',
  CHART: 'chart',
  ALERTS: 'alerts',
  // Paper Trading
  PAPER_ORDERS: 'paper-orders',
  PAPER_POSITIONS: 'paper-positions',
  // Analysis
  SIGNALS: 'signals',
  OPPORTUNITIES: 'opportunities',
  COIN_DOSSIER: 'coin-dossier',
  // AI
  AI_EVALUATE: 'ai-evaluate',
  // Market Data
  MARKET_WATCH: 'market-watch',
  INGESTION_STATUS: 'ingestion-status',
  // Portfolio & Risk
  PORTFOLIO: 'portfolio',
  WATCHLIST: 'watchlist',
  TRADE_HISTORY: 'trade-history',
  RISK_CALCULATOR: 'risk-calculator',
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
      { id: VIEW_IDS.ALERTS, label: 'Alerts', icon: '🔔', status: 'new' },
    ],
  },
  {
    id: 'paper-trading',
    title: 'Paper Trading',
    items: [
      { id: VIEW_IDS.PAPER_ORDERS, label: 'Orders', icon: '📝', status: 'ready' },
      { id: VIEW_IDS.PAPER_POSITIONS, label: 'Positions', icon: '💼', status: 'ready' },
    ],
  },
  {
    id: 'portfolio',
    title: 'Portfolio & Risk',
    items: [
      { id: VIEW_IDS.PORTFOLIO, label: 'Portfolio', icon: '💼', status: 'new' },
      { id: VIEW_IDS.WATCHLIST, label: 'Watchlist', icon: '⭐', status: 'new' },
      { id: VIEW_IDS.TRADE_HISTORY, label: 'Trade History', icon: '📜', status: 'new' },
      { id: VIEW_IDS.RISK_CALCULATOR, label: 'Risk Calculator', icon: '🎲', status: 'new' },
    ],
  },
  {
    id: 'analysis',
    title: 'Analysis',
    items: [
      { id: VIEW_IDS.SIGNALS, label: 'Signals', icon: '🎯', status: 'ready' },
      { id: VIEW_IDS.OPPORTUNITIES, label: 'Opportunities', icon: '💡', status: 'beta' },
      { id: VIEW_IDS.COIN_DOSSIER, label: 'Dossiers', icon: '📁', status: 'new' },
    ],
  },
  {
    id: 'ai',
    title: 'AI',
    items: [
      { id: VIEW_IDS.AI_EVALUATE, label: 'Multi-Brain', icon: '🧠', status: 'new' },
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
