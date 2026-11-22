import { http, type ReqOpts } from "@/lib/http"
import type {
  CorpusBuilderResult,
  IngestFileRequest,
  IngestWebRequest,
  JobCreatedResponse,
  JobStatusResponse,
  SearchAgenticRequest,
  SearchAgenticResponse,
  SearchRequest,
  SearchResultResponse,
} from "@/types/Index"

export const knowledgeApi = {
  ingestFile: (body: IngestFileRequest) =>
    http.post<CorpusBuilderResult>("/knowledge/ingest/file", body),

  ingestWeb: (body: IngestWebRequest) =>
    http.post<JobCreatedResponse>("/knowledge/ingest/web", body),

  job: (jobId: number, opts?: ReqOpts) =>
    http.get<JobStatusResponse>(`/knowledge/ingest/jobs/${jobId}`, opts),

  search: (body: SearchRequest, opts?: ReqOpts) =>
    http.post<SearchResultResponse[]>("/knowledge/search", body, opts),

  searchAgentic: (body: SearchAgenticRequest, opts?: ReqOpts) =>
    http.post<SearchAgenticResponse>("/knowledge/search/agentic", body, opts),
}