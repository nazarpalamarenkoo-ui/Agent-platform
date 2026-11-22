import { http, type ReqOpts } from "@/lib/http"
import type {
  AdminUserRead,
  AdminUsersParams,
  RoleUpdate,
  TokenLimitUpdate,
} from "@/types/Index"

export const adminApi = {
  admins: (opts?: ReqOpts) => http.get<AdminUserRead[]>("/admin/admins", opts),

  setRole: (id: number, body: RoleUpdate) =>
    http.put<AdminUserRead>(`/admin/users/${id}/role`, body),

  users: (params?: AdminUsersParams, opts?: ReqOpts) =>
    http.get<AdminUserRead[]>("/admin/users", { query: params, ...opts }),

  user: (id: number, opts?: ReqOpts) =>
    http.get<AdminUserRead>(`/admin/users/${id}`, opts),

  setTokenLimit: (id: number, body: TokenLimitUpdate) =>
    http.put<AdminUserRead>(`/admin/users/${id}/token-limit`, body),

  resetUsage: (id: number) =>
    http.post<AdminUserRead>(`/admin/users/${id}/reset-usage`),
}