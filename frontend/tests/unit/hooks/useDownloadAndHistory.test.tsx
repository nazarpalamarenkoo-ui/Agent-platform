import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import { setToken } from "@/auth/session"
import { useAuth } from "@/auth/useAuth"
import { downloadErrorMessage, useDownload } from "@/hooks/useDownload"
import {
  recordDownload,
  useBundleZip,
  useDownloadHistory,
} from "@/hooks/useDownloadHistory"
import { ApiError } from "@/lib/http"
import type { ConfigBundleRead } from "@/types/Index"
import { server } from "../../server"

const BASE = "http://localhost:8000"

const sampleBundle: ConfigBundleRead = {
  id: 8,
  user_id: 1,
  agent_id: 2,
  name: "Backend Pack",
  description: "API tools",
  skills: [],
  tools: [],
  knowledge_packs: [],
}

const originalCreate = URL.createObjectURL
const originalRevoke = URL.revokeObjectURL
let savedFiles: string[] = []

beforeEach(() => {
  savedFiles = []
  URL.createObjectURL = vi.fn(() => "blob:fake")
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    savedFiles.push(this.download)
  })
})

afterEach(() => {
  URL.createObjectURL = originalCreate
  URL.revokeObjectURL = originalRevoke
  vi.restoreAllMocks()
})

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe("useDownload and downloadErrorMessage", () => {
  it("formats download error messages for 404, network error, and generic errors", () => {
    expect(downloadErrorMessage(new ApiError(404, "Not found"))).toBe(
      "Nothing to download: it no longer exists.",
    )
    expect(downloadErrorMessage(new ApiError(0, "Network"))).toBe("Can't reach the server.")
    expect(downloadErrorMessage(new ApiError(500, "Server boom"))).toBe("Server boom")
  })

  it("saves downloaded file with server filename or fallbackName", async () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useDownload(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        fallbackName: "fallback.zip",
        load: async () => ({ blob: new Blob(["data"]), filename: null }),
      })
    })

    expect(savedFiles).toEqual(["fallback.zip"])
  })
})

describe("useDownloadHistory and useBundleZip", () => {
  it("records, deduplicates by bundleId, caps at 8 items, and reacts to updates", () => {
    const { result } = renderHook(() => useDownloadHistory(1))
    expect(result.current).toEqual([])

    act(() => {
      for (let i = 1; i <= 10; i++) {
        recordDownload(1, {
          bundleId: i,
          name: `Bundle ${i}`,
          filename: `bundle-${i}.zip`,
          at: `2026-11-22T10:00:0${i % 10}Z`,
        })
      }
    })

    expect(result.current).toHaveLength(8)
    expect(result.current[0].bundleId).toBe(10)

    act(() => {
      recordDownload(1, {
        bundleId: 5,
        name: "Bundle 5 Updated",
        filename: "bundle-5-v2.zip",
        at: "2026-11-22T11:00:00Z",
      })
    })

    expect(result.current[0]).toMatchObject({
      bundleId: 5,
      name: "Bundle 5 Updated",
      filename: "bundle-5-v2.zip",
    })
    expect(result.current).toHaveLength(8)
  })

  it("downloads bundle zip and records it in user's download history", async () => {
    setToken("tok")
    server.use(
      mock.get(`${BASE}/users/me`, () =>
        HttpResponse.json({
          id: 1,
          username: "alice",
          email: "alice@example.com",
          role: "user",
          tokens_used: 0,
          token_limit: 1000,
        }),
      ),
      mock.get(`${BASE}/config-bundles/8/export`, () =>
        new HttpResponse("zip-data", {
          headers: {
            "Content-Disposition": 'attachment; filename="backend-pack.zip"',
          },
        }),
      ),
    )

    const wrapper = createWrapper()
    const { result } = renderHook(
      () => ({
        auth: useAuth(),
        zip: useBundleZip(),
        history: useDownloadHistory(1),
      }),
      { wrapper },
    )

    await waitFor(() => expect(result.current.auth.user?.id).toBe(1))

    act(() => {
      result.current.zip.start(sampleBundle)
    })

    await waitFor(() => expect(savedFiles).toContain("backend-pack.zip"))
    await waitFor(() =>
      expect(result.current.history[0]).toMatchObject({
        bundleId: 8,
        name: "Backend Pack",
        filename: "backend-pack.zip",
      }),
    )
  })
})
