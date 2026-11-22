import { http, type ReqOpts } from "@/lib/http"
import type {
  PaginationParams,
  ToolCreate,
  ToolRead,
  ToolsParams,
  ToolUpdate,
} from "@/types/Index"

export const toolsApi = {
  list: (params?: ToolsParams, opts?: ReqOpts) =>
    http.get<ToolRead[]>("/tools", { query: params, ...opts }),

  byDomain: (domainId: number, params?: PaginationParams, opts?: ReqOpts) =>
    http.get<ToolRead[]>(`/tools/by-domain/${domainId}`, { query: params, ...opts }),

  get: (id: number, opts?: ReqOpts) => http.get<ToolRead>(`/tools/${id}`, opts),

  create: (body: ToolCreate) => http.post<ToolRead>("/tools", body),
  update: (id: number, body: ToolUpdate) =>
    http.put<ToolRead>(`/tools/${id}`, body),
  archive: (id: number) => http.post<ToolRead>(`/tools/${id}/archive`),
  restore: (id: number) => http.post<ToolRead>(`/tools/${id}/restore`),
}