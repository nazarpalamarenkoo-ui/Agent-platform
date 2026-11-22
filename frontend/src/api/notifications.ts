import { http, type ReqOpts } from "@/lib/http"
import type {
  MarkedRead,
  NotificationRead,
  NotificationsParams,
  UnreadCount,
} from "@/types/Index"

export const notificationsApi = {
  list: (params?: NotificationsParams, opts?: ReqOpts) =>
    http.get<NotificationRead[]>("/notifications", { query: params, ...opts }),

  unreadCount: (opts?: ReqOpts) =>
    http.get<UnreadCount>("/notifications/unread-count", opts),

  markAllRead: () => http.post<MarkedRead>("/notifications/read-all"),

  markRead: (id: number) => http.post<void>(`/notifications/${id}/read`),
}