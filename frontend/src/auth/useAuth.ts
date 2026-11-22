import { useCallback, useSyncExternalStore } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { authApi, usersApi } from "@/api"
import { clearSession, getToken, setToken, subscribe } from "@/auth/session"
import type { SignInArgs } from "@/types/Index"

export const ME_QUERY_KEY = ["me"] as const

export function useAuth() {
  const token = useSyncExternalStore(subscribe, getToken, getToken)
  const queryClient = useQueryClient()

  const meQuery = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: ({ signal }) => usersApi.me({ signal }),
    enabled: token !== null,
    staleTime: 60_000,
  })

  const user = token !== null ? meQuery.data : undefined

  const loginWithToken = useCallback(
    (accessToken: string) => {
      queryClient.clear()
      setToken(accessToken)
    },
    [queryClient],
  )

  const login = useCallback(
    async (args: SignInArgs) => {
      const result = await authApi.login(args)
      loginWithToken(result.access_token)
    },
    [loginWithToken],
  )

  const logout = useCallback(() => {
    clearSession()
    queryClient.clear()
  }, [queryClient])

  return {
    token,
    user,
    isAuthenticated: token !== null,
    isLoading: token !== null && meQuery.isPending,
    isAdmin: user?.role === "admin" || user?.role === "super_admin",
    isSuperAdmin: user?.role === "super_admin",
    login,
    loginWithToken,
    logout,
  }
}