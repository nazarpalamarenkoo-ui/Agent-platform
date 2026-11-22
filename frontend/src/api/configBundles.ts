import { http, type ReqOpts } from "@/lib/http"
import type {
  BundleItems,
  ConfigBundleClone,
  ConfigBundleCreate,
  ConfigBundleFromAgent,
  ConfigBundleRead,
  ConfigBundlesParams,
  ConfigBundleUpdate,
  EffectiveBundleRead,
} from "@/types/Index"

export const configBundlesApi = {
  list: (params?: ConfigBundlesParams, opts?: ReqOpts) =>
    http.get<ConfigBundleRead[]>("/config-bundles", { query: params, ...opts }),

  get: (id: number, opts?: ReqOpts) =>
    http.get<ConfigBundleRead>(`/config-bundles/${id}`, opts),

  effective: (id: number, opts?: ReqOpts) =>
    http.get<EffectiveBundleRead>(`/config-bundles/${id}/effective`, opts),

  create: (body: ConfigBundleCreate) =>
    http.post<ConfigBundleRead>("/config-bundles", body),

  createFromAgent: (body: ConfigBundleFromAgent) =>
    http.post<ConfigBundleRead>("/config-bundles/from-agent", body),

  update: (id: number, body: ConfigBundleUpdate) =>
    http.patch<ConfigBundleRead>(`/config-bundles/${id}`, body),

  remove: (id: number) => http.delete(`/config-bundles/${id}`),

  clone: (id: number, body: ConfigBundleClone) =>
    http.post<ConfigBundleRead>(`/config-bundles/${id}/clone`, body),

  addItems: (id: number, body: BundleItems) =>
    http.post<ConfigBundleRead>(`/config-bundles/${id}/items`, body),

  removeItems: (id: number, body: BundleItems) =>
    http.post<ConfigBundleRead>(`/config-bundles/${id}/items/remove`, body),

  exportZip: (id: number, opts?: ReqOpts) =>
    http.download(`/config-bundles/${id}/export`, opts),
}
