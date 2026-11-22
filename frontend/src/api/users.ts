import { http, type ReqOpts } from "@/lib/http"
import type { ChangePassword, UserRead, UserUpdate } from "@/types/Index"

export const usersApi = {
  me: (opts?: ReqOpts) => http.get<UserRead>("/users/me", opts),

  get: (id: number, opts?: ReqOpts) => http.get<UserRead>(`/users/${id}`, opts),

  update: (id: number, body: UserUpdate) =>
    http.patch<UserRead>(`/users/${id}`, body),

  changePassword: (id: number, body: ChangePassword) =>
    http.post<void>(`/users/${id}/change-password`, body),

  remove: (id: number) => http.delete(`/users/${id}`),
}