import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { notificationsApi } from "@/api"

const ROOT = ["notifications"] as const

export const notificationKeys = {
  list: [...ROOT, "list"] as const,
  unread: [...ROOT, "unread"] as const,
}

export function useNotifications() {
  return useQuery({
    queryKey: notificationKeys.list,
    queryFn: ({ signal }) => notificationsApi.list({ limit: 100 }, { signal }),
  })
}

export function useUnreadCount() {
  return useQuery({
    queryKey: notificationKeys.unread,
    queryFn: ({ signal }) => notificationsApi.unreadCount({ signal }),
    refetchInterval: 60_000,
    select: (data) => data.unread,
  })
}

function useRefreshNotifications() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ROOT })
}

export function useMarkRead() {
  const refresh = useRefreshNotifications()
  return useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: refresh,
  })
}

export function useMarkAllRead() {
  const refresh = useRefreshNotifications()
  return useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: refresh,
  })
}