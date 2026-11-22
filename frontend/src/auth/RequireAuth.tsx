import type { ReactNode } from "react"
import { Navigate, Outlet, useLocation } from "react-router"
import { useAuth } from "@/auth/useAuth"

interface RequireAuthProps {
  role?: "admin" | "super_admin"
  fallback?: ReactNode
}

export function RequireAuth({ role, fallback = null }: RequireAuthProps) {
  const { isAuthenticated, isLoading, isAdmin, isSuperAdmin } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  if (isLoading) return <>{fallback}</>

  if (role === "admin" && !isAdmin) return <Navigate to="/" replace />
  if (role === "super_admin" && !isSuperAdmin) return <Navigate to="/" replace />

  return <Outlet />
}