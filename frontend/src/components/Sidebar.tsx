import { PanelLeft, PanelLeftClose } from 'lucide-react'
import { NAV_GROUPS, type ViewId } from '../nav'

interface SidebarProps {
  activeViewId: ViewId
  onSelectView: (id: ViewId) => void
  collapsed: boolean
  onToggleCollapsed: () => void
}

export default function Sidebar({
  activeViewId,
  onSelectView,
  collapsed,
  onToggleCollapsed,
}: SidebarProps) {
  return (
    <aside
      className={`flex h-full flex-col border-r border-gray-200 bg-white transition-all dark:border-gray-800 dark:bg-gray-900 ${
        collapsed ? 'w-14' : 'w-48'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-3 py-3 dark:border-gray-800">
        {!collapsed && (
          <span className="text-sm font-bold text-gray-900 dark:text-gray-100">
            cryptotrader
          </span>
        )}
        <button
          onClick={onToggleCollapsed}
          className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.id} className="mb-3">
            {!collapsed && (
              <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-500">
                {group.title}
              </div>
            )}

            {group.items.map((item) => {
              const isActive = activeViewId === item.id

              return (
                <button
                  key={item.id}
                  className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100'
                  } ${collapsed ? 'justify-center' : ''}`}
                  onClick={() => onSelectView(item.id)}
                  title={collapsed ? item.label : undefined}
                >
                  <span className="text-base">{item.icon}</span>
                  {!collapsed && (
                    <>
                      <span className="flex-1 text-left">{item.label}</span>
                      {item.status === 'new' && (
                        <span className="rounded bg-green-100 px-1 py-0.5 text-[9px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
                          new
                        </span>
                      )}
                      {item.status === 'beta' && (
                        <span className="rounded bg-yellow-100 px-1 py-0.5 text-[9px] font-medium text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
                          beta
                        </span>
                      )}
                    </>
                  )}
                </button>
              )
            })}
          </div>
        ))}
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div className="border-t border-gray-200 px-3 py-2 dark:border-gray-800">
          <div className="text-[10px] text-gray-400 dark:text-gray-600">
            v2.0 • Bitfinex
          </div>
        </div>
      )}
    </aside>
  )
}
