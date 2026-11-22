import { clearSession, getToken } from "@/auth/session"
import type { ValidationErrorItem } from "@/types/Index"

const rawBase = import.meta.env.VITE_API_URL as string | undefined

export const API_URL = (rawBase ?? "http://localhost:8000").replace(/\/+$/, "")

export interface ReqOpts {
  signal?: AbortSignal
}

export interface RequestConfig extends ReqOpts {
  query?: object
  auth?: boolean
}

type ErrorDetail = string | ValidationErrorItem[] | null

export class ApiError extends Error {
  readonly status: number
  readonly detail: ErrorDetail
  readonly retryAfter: number | null

  constructor(
    status: number,
    message: string,
    detail: ErrorDetail = null,
    retryAfter: number | null = null,
  ) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
    this.retryAfter = retryAfter
  }

  get fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {}
    if (!Array.isArray(this.detail)) return result
    for (const item of this.detail) {
      const field = item.loc[item.loc.length - 1]
      if (field === undefined) continue
      const key = String(field)
      if (!(key in result)) result[key] = item.msg
    }
    return result
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function getErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  return error instanceof Error ? error.message : fallback
}

export interface DownloadedFile {
  blob: Blob
  filename: string | null
}

export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null

  const encoded = /filename\*\s*=\s*utf-8''([^;]+)/i.exec(header)
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1].trim())
    } catch {
    }
  }

  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header)
  return plain?.[1]?.trim() || null
}

function buildUrl(path: string, query?: object): string {
  const params = new URLSearchParams()
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue
      params.set(key, String(value))
    }
  }
  const qs = params.toString()
  return `${API_URL}${path}${qs ? `?${qs}` : ""}`
}

function parseBody(text: string): unknown {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function toApiError(response: Response, data: unknown): ApiError {
  let detail: ErrorDetail = null
  let message = `Error ${response.status}`

  if (data !== null && typeof data === "object" && "detail" in data) {
    const raw = (data as { detail: unknown }).detail
    if (typeof raw === "string") {
      detail = raw
      message = raw
    } else if (Array.isArray(raw)) {
      detail = raw as ValidationErrorItem[]
      message = detail.map((item) => item.msg).join("; ") || message
    }
  }

  const retry = Number(response.headers.get("Retry-After"))
  return new ApiError(response.status, message, detail, retry > 0 ? retry : null)
}

async function send(
  method: string,
  path: string,
  body: unknown,
  config: RequestConfig = {},
): Promise<Response> {
  const { query, auth = true, signal } = config

  const headers: Record<string, string> = { Accept: "application/json" }
  if (body !== undefined) headers["Content-Type"] = "application/json"
  if (auth) {
    const token = getToken()
    if (token) headers["Authorization"] = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if ((error as { name?: string } | null)?.name === "AbortError") throw error
    throw new ApiError(0, "Can't reach the server")
  }

  if (!response.ok) {
    const data = parseBody(await response.text())
    if (response.status === 401 && auth) clearSession()
    throw toApiError(response, data)
  }

  return response
}

async function request<T>(
  method: string,
  path: string,
  body: unknown,
  config?: RequestConfig,
): Promise<T> {
  const response = await send(method, path, body, config)
  if (response.status === 204) return undefined as T
  return parseBody(await response.text()) as T
}

async function download(path: string, config?: RequestConfig): Promise<DownloadedFile> {
  const response = await send("GET", path, undefined, config)
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("Content-Disposition")),
  }
}

export const http = {
  get: <T>(path: string, config?: RequestConfig) =>
    request<T>("GET", path, undefined, config),
  post: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    request<T>("POST", path, body, config),
  put: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    request<T>("PUT", path, body, config),
  patch: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    request<T>("PATCH", path, body, config),
  delete: <T = void>(path: string, config?: RequestConfig) =>
    request<T>("DELETE", path, undefined, config),
  download,
}
