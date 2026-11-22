import { http, type ReqOpts } from "@/lib/http"
import type {
  MySkillCreate,
  MySkillImport,
  MySkillRead,
  MySkillsParams,
  MySkillSummary,
  MySkillUpdate,
  SkillDraftConfirm,
  SkillDraftJobResponse,
  SkillDraftRequest,
  SkillDraftStatus,
} from "@/types/Index"

export const mySkillsApi = {
  list: (params?: MySkillsParams, opts?: ReqOpts) =>
    http.get<MySkillSummary[]>("/my/skills", { query: params, ...opts }),

  get: (id: number, opts?: ReqOpts) => http.get<MySkillRead>(`/my/skills/${id}`, opts),

  create: (body: MySkillCreate) => http.post<MySkillRead>("/my/skills", body),

  importMarkdown: (body: MySkillImport) =>
    http.post<MySkillRead>("/my/skills/import", body),

  update: (id: number, body: MySkillUpdate) =>
    http.put<MySkillRead>(`/my/skills/${id}`, body),

  archive: (id: number) => http.post<MySkillRead>(`/my/skills/${id}/archive`),
  restore: (id: number) => http.post<MySkillRead>(`/my/skills/${id}/restore`),

  downloadMarkdown: (id: number, opts?: ReqOpts) =>
    http.download(`/my/skills/${id}/download`, opts),


  requestDraft: (body: SkillDraftRequest) =>
    http.post<SkillDraftJobResponse>("/my/skills/drafts", body),

  draftStatus: (jobId: number, opts?: ReqOpts) =>
    http.get<SkillDraftStatus>(`/my/skills/drafts/${jobId}`, opts),

  confirmDraft: (jobId: number, body: SkillDraftConfirm) =>
    http.post<MySkillRead>(`/my/skills/drafts/${jobId}/confirm`, body),
}
