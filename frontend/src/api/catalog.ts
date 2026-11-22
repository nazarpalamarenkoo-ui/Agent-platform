import { http, type ReqOpts } from "@/lib/http"
import type { HintRequest, HintResponse } from "@/types/Index"

export const catalogApi = {
  hint: (body: HintRequest, opts?: ReqOpts) =>
    http.post<HintResponse>("/catalog/hint", body, opts),
}