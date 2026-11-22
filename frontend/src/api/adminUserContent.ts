import { http, type ReqOpts } from "@/lib/http"
import type {
  AdminSkillListItem,
  AdminSkillRead,
  AdminToolItem,
  AdminUserSkillsParams,
  AdminUserToolsParams,
  ArchiveForViolation,
  UserOverview,
} from "@/types/Index"

export const adminUserContentApi = {
  overview: (userId: number, opts?: ReqOpts) =>
    http.get<UserOverview>(`/admin/users/${userId}/overview`, opts),

  skills: (userId: number, params?: AdminUserSkillsParams, opts?: ReqOpts) =>
    http.get<AdminSkillListItem[]>(`/admin/users/${userId}/skills`, {
      query: params,
      ...opts,
    }),

  skill: (userId: number, skillId: number, opts?: ReqOpts) =>
    http.get<AdminSkillRead>(`/admin/users/${userId}/skills/${skillId}`, opts),

  archiveSkill: (userId: number, skillId: number, body: ArchiveForViolation) =>
    http.post<AdminSkillListItem>(
      `/admin/users/${userId}/skills/${skillId}/archive`,
      body,
    ),

  tools: (userId: number, params?: AdminUserToolsParams, opts?: ReqOpts) =>
    http.get<AdminToolItem[]>(`/admin/users/${userId}/tools`, {
      query: params,
      ...opts,
    }),
}