import { http, type ReqOpts } from "@/lib/http"
import type {
  AgentCreate,
  AgentRead,
  AgentsParams,
  AgentUpdate,
  CustomAgentCreate,
  CustomAgentRead,
} from "@/types/Index"

export const agentsApi = {
  list: (params?: AgentsParams, opts?: ReqOpts) =>
    http.get<AgentRead[]>("/agents", { query: params, ...opts }),

  get: (id: number, opts?: ReqOpts) => http.get<AgentRead>(`/agents/${id}`, opts),

  createCustom: (body: CustomAgentCreate) =>
    http.post<CustomAgentRead>("/agents/custom", body),

  create: (body: AgentCreate) => http.post<AgentRead>("/agents", body),
  update: (id: number, body: AgentUpdate) =>
    http.put<AgentRead>(`/agents/${id}`, body),
  archive: (id: number) => http.post<AgentRead>(`/agents/${id}/archive`),
  restore: (id: number) => http.post<AgentRead>(`/agents/${id}/restore`),
}