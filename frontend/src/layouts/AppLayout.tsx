import { NavLink, Outlet } from "react-router"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/auth/useAuth"
import { useUnreadCount } from "@/hooks/useNotifications"
import { APP_NAME } from "@/lib/brand"
import { cn } from "@/lib/utils"

interface NavItem {
  to: string
  label: string
  end?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Profile", end: true },
  { to: "/config", label: "Configurator" },
]

const ADMIN_ITEMS: NavItem[] = [{ to: "/admin/users", label: "Users" }]

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-1.5 whitespace-nowrap border-b-2 py-1 transition-colors",
    isActive
      ? "border-red text-foreground"
      : "border-transparent text-muted-foreground hover:text-foreground",
  )

export function AppLayout() {
  const { user, isAdmin, logout } = useAuth()
  const unread = useUnreadCount().data ?? 0
  const items = isAdmin ? [...NAV_ITEMS, ...ADMIN_ITEMS] : NAV_ITEMS

  return (
    <div className="min-h-screen">
      <header className="border-b border-hairline/15">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-8 px-6">
          <span className="font-serif text-lg">{APP_NAME}</span>

          <nav
            className="flex min-w-0 gap-6 overflow-x-auto text-sm"
            aria-label="Main navigation"
          >
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-4 text-sm">
            <NavLink to="/notifications" className={linkClass}>
              Notifications
              {unread > 0 ? (
                <span
                  aria-label={`${unread} unread`}
                  className="rounded-full bg-red px-1.5 font-mono text-[10px] leading-4 text-white"
                >
                  {unread > 99 ? "99+" : unread}
                </span>
              ) : null}
            </NavLink>
            <span className="font-mono text-xs text-muted-foreground">{user?.username}</span>
            <Button variant="ghost" size="sm" onClick={logout}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main>
        <Outlet />
      </main>
    </div>
  )
}