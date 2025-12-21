import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

type Theme = 'light' | 'dark'

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  const saved = window.localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark') return saved
  return 'dark'
}

function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

type PanelProps = {
  title: string
  subtitle?: string
  children?: ReactNode
}

function Panel({ title, subtitle, children }: PanelProps) {
  return (
    <details open className="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900">
      <summary className="cursor-pointer select-none list-none">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs font-semibold tracking-wide text-gray-900 dark:text-gray-100">{title}</div>
            {subtitle ? <div className="text-xs text-gray-600 dark:text-gray-400">{subtitle}</div> : null}
          </div>
          <div className="shrink-0 select-none text-xs text-gray-500 dark:text-gray-400">
            <span className="ct-caret inline-block">^</span>
          </div>
        </div>
      </summary>
      <div className="mt-2 text-sm text-gray-800 dark:text-gray-200">{children}</div>
    </details>
  )
}

function Kvp({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-gray-600 dark:text-gray-400">{k}</span>
      <span className="text-xs">{v}</span>
    </div>
  )
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(() => getInitialTheme())
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    applyTheme(theme)
    window.localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    if (!settingsOpen) return

    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setSettingsOpen(false)
    }

    const onMouseDown = (ev: MouseEvent) => {
      const el = settingsRef.current
      if (!el) return
      if (ev.target instanceof Node && !el.contains(ev.target)) {
        setSettingsOpen(false)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('mousedown', onMouseDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('mousedown', onMouseDown)
    }
  }, [settingsOpen])

  const nextThemeLabel = useMemo(() => (theme === 'dark' ? 'light' : 'dark'), [theme])

  return (
    <div className="min-h-screen bg-gray-50 text-sm text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-10 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-3 py-2">
            <div className="text-sm font-semibold">cryptotrader</div>
            <div className="flex items-center gap-3">
              <div className="text-xs text-gray-600 dark:text-gray-400">dashboard</div>

              <div ref={settingsRef} className="relative">
                <button
                  type="button"
                  aria-label="Settings"
                  className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                  onClick={() => setSettingsOpen(!settingsOpen)}
                >
                  ⚙
                </button>

                {settingsOpen ? (
                  <div className="absolute right-0 mt-2 w-56 rounded-md border border-gray-200 bg-white p-2 text-xs text-gray-700 shadow-sm dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="font-semibold">Settings</div>
                      <button
                        type="button"
                        className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                        onClick={() => setSettingsOpen(false)}
                      >
                        x
                      </button>
                    </div>

                    <div className="flex items-center justify-between gap-2 rounded border border-gray-200 bg-white px-2 py-2 dark:border-gray-800 dark:bg-gray-900">
                      <span className="text-gray-600 dark:text-gray-400">Theme</span>
                      <button
                        type="button"
                        className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                      >
                        {nextThemeLabel}
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-3 py-3">
          <div className="ct-dock-grid gap-3">
            <div className="ct-dock-left flex flex-col gap-3">
              <Panel title="Market Watch" subtitle="Symbols / tickers">
                <Kvp k="Primary" v="BTCUSD" />
                <div className="mt-2 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-600 dark:text-gray-400">BTCUSD</span>
                    <span>—</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-600 dark:text-gray-400">ETHUSD</span>
                    <span>—</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-600 dark:text-gray-400">SOLUSD</span>
                    <span>—</span>
                  </div>
                </div>
              </Panel>

              <Panel title="Market Data" subtitle="Bitfinex candles (OHLCV)">
                <Kvp k="Status" v="Not connected" />
                <div className="mt-2">
                  <Kvp k="Latest run" v="—" />
                </div>
              </Panel>
            </div>

            <div className="ct-dock-center flex flex-col gap-3">
              <Panel title="Chart" subtitle="Price + volume">
                <div className="rounded border border-dashed border-gray-200 bg-gray-50 p-3 text-xs text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400">
                  Chart placeholder (future: candles + indicators).
                </div>
              </Panel>

              <div className="ct-dock-bottom flex flex-col gap-3">
                <Panel title="Terminal" subtitle="Orders / positions / logs">
                  <Kvp k="Orders" v="0" />
                  <div className="mt-2">
                    <Kvp k="Positions" v="0" />
                  </div>
                  <div className="mt-2 rounded border border-gray-200 bg-white p-2 text-[11px] text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
                    <div className="font-mono">[log] service online</div>
                    <div className="font-mono">[log] waiting for backend</div>
                  </div>
                </Panel>
              </div>
            </div>

            <div className="ct-dock-right flex flex-col gap-3">
              <Panel title="Opportunities" subtitle="Signals snapshot">
                <Kvp k="Top symbol" v="—" />
                <div className="mt-2">
                  <Kvp k="Score" v="—" />
                </div>
              </Panel>

              <Panel title="Data Quality" subtitle="Candle gaps">
                <Kvp k="Open gaps" v="—" />
                <div className="mt-2">
                  <Kvp k="Last repair" v="—" />
                </div>
              </Panel>

              <Panel title="Execution" subtitle="Intents / results">
                <Kvp k="Mode" v="dry-run" />
                <div className="mt-2">
                  <Kvp k="Last order" v="—" />
                </div>
              </Panel>

              <Panel title="System" subtitle="Health">
                <Kvp k="Backend" v="—" />
                <div className="mt-2">
                  <Kvp k="Database" v="—" />
                </div>
              </Panel>
            </div>
          </div>
        </main>

        <footer className="sticky bottom-0 border-t border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-3 py-2 text-xs text-gray-600 dark:text-gray-400">
            <span>v2 skeleton</span>
            <span>paper-trading default</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
