import { http, type ReqOpts } from "@/lib/http"
import type { DomainCreate, DomainRead, PaginationParams } from "@/types/Index"

export const domainsApi = {
  list: (params?: PaginationParams, opts?: ReqOpts) =>
    http.get<DomainRead[]>("/domains", { query: params, ...opts }),

  roots: (opts?: ReqOpts) => http.get<DomainRead[]>("/domains/roots", opts),

  get: (id: number, opts?: ReqOpts) =>
    http.get<DomainRead>(`/domains/${id}`, opts),

  create: (body: DomainCreate) => http.post<DomainRead>("/domains", body),
}