import { http, type ReqOpts } from "@/lib/http"
import type {
  MyToolCreate,
  MyToolRead,
  MyToolResponse,
  MyToolsParams,
  MyToolUpdate,
} from "@/types/Index"

export const myToolsApi = {
  list: (params?: MyToolsParams, opts?: ReqOpts) =>
    http.get<MyToolRead[]>("/my/tools", { query: params, ...opts }),

  get: (id: number, opts?: ReqOpts) => http.get<MyToolRead>(`/my/tools/${id}`, opts),

  create: (body: MyToolCreate) => http.post<MyToolResponse>("/my/tools", body),

  update: (id: number, body: MyToolUpdate) =>
    http.put<MyToolResponse>(`/my/tools/${id}`, body),

  archive: (id: number) => http.post<MyToolRead>(`/my/tools/${id}/archive`),
  restore: (id: number) => http.post<MyToolRead>(`/my/tools/${id}/restore`),
}