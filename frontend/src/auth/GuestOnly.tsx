import { Navigate, Outlet, useLocation } from "react-router"
import { useAuth } from "@/auth/useAuth"

export function GuestOnly() {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  if (isAuthenticated) {
    const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname
    return <Navigate to={from ?? "/"} replace />
  }
  return <Outlet />
}