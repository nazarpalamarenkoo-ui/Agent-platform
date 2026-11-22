import { http, type ReqOpts } from "@/lib/http"
import type {
  KnowledgePackCreate,
  KnowledgePackRead,
  KnowledgePacksParams,
  PaginationParams,
} from "@/types/Index"

export const knowledgePacksApi = {
  list: (params?: KnowledgePacksParams, opts?: ReqOpts) =>
    http.get<KnowledgePackRead[]>("/knowledge-packs", { query: params, ...opts }),

  byDomain: (domainId: number, params?: PaginationParams, opts?: ReqOpts) =>
    http.get<KnowledgePackRead[]>(`/knowledge-packs/by-domain/${domainId}`, {
      query: params,
      ...opts,
    }),

  bySlug: (slug: string, opts?: ReqOpts) =>
    http.get<KnowledgePackRead>(`/knowledge-packs/${encodeURIComponent(slug)}`, opts),

  create: (body: KnowledgePackCreate) =>
    http.post<KnowledgePackRead>("/knowledge-packs", body),
  archive: (id: number) =>
    http.post<KnowledgePackRead>(`/knowledge-packs/${id}/archive`),
  restore: (id: number) =>
    http.post<KnowledgePackRead>(`/knowledge-packs/${id}/restore`),
}