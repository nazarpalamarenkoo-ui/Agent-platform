import { http, type ReqOpts } from "@/lib/http"
import type {
  DeviceRead,
  DevicesParams,
  DeviceTokenCreate,
  DeviceTokenIssued,
} from "@/types/Index"

export const deviceApi = {

  issueToken: (body: DeviceTokenCreate) =>
    http.post<DeviceTokenIssued>("/device/tokens", body),

  list: (params?: DevicesParams, opts?: ReqOpts) =>
    http.get<DeviceRead[]>("/device", { query: params, ...opts }),

  revoke: (deviceId: number) =>
    http.post<DeviceRead>(`/device/${deviceId}/revoke`),
}