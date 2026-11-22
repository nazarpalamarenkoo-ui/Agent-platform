import { http, type ReqOpts } from "@/lib/http"
import type {
  PaginationParams,
  SkillCreate,
  SkillRead,
  SkillsParams,
  SkillUpdate,
} from "@/types/Index"

export const skillsApi = {
  list: (params?: SkillsParams, opts?: ReqOpts) =>
    http.get<SkillRead[]>("/skills", { query: params, ...opts }),

  byDomain: (domainId: number, params?: PaginationParams, opts?: ReqOpts) =>
    http.get<SkillRead[]>(`/skills/by-domain/${domainId}`, { query: params, ...opts }),

  get: (id: number, opts?: ReqOpts) => http.get<SkillRead>(`/skills/${id}`, opts),

  downloadMarkdown: (id: number, opts?: ReqOpts) =>
    http.download(`/skills/${id}/download`, opts),

  create: (body: SkillCreate) => http.post<SkillRead>("/skills", body),
  update: (id: number, body: SkillUpdate) =>
    http.put<SkillRead>(`/skills/${id}`, body),
  archive: (id: number) => http.post<SkillRead>(`/skills/${id}/archive`),
  restore: (id: number) => http.post<SkillRead>(`/skills/${id}/restore`),
}