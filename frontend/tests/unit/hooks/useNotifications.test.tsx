import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  useUnreadCount,
} from "@/hooks/useNotifications"
import { server } from "../../server"

const BASE = "http://localhost:8000"

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { wrapper, invalidate }
}

describe("useNotifications hooks", () => {
  it("loads notifications list and selects unread number from unreadCount", async () => {
    server.use(
      mock.get(`${BASE}/notifications`, () =>
        HttpResponse.json([
          {
            id: 1,
            type: "skill_archived",
            skill_id: 10,
            tool_id: null,
            item_name: "Docker Skill",
            read_at: null,
            created_at: "2026-11-22T10:00:00Z",
          },
        ]),
      ),
      mock.get(`${BASE}/notifications/unread-count`, () => HttpResponse.json({ unread: 3 })),
    )

    const { wrapper } = createWrapper()
    const list = renderHook(() => useNotifications(), { wrapper })
    const unread = renderHook(() => useUnreadCount(), { wrapper })

    await waitFor(() => expect(list.result.current.data).toHaveLength(1))
    await waitFor(() => expect(unread.result.current.data).toBe(3))
  })

  it("marks single and all notifications as read and invalidates notification queries", async () => {
    server.use(
      mock.post(`${BASE}/notifications/1/read`, () => new HttpResponse(null, { status: 204 })),
      mock.post(`${BASE}/notifications/read-all`, () => HttpResponse.json({ updated: 3 })),
    )

    const { wrapper, invalidate } = createWrapper()
    const markOne = renderHook(() => useMarkRead(), { wrapper })
    const markAll = renderHook(() => useMarkAllRead(), { wrapper })

    await act(async () => {
      await markOne.result.current.mutateAsync(1)
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["notifications"] })

    await act(async () => {
      await markAll.result.current.mutateAsync()
    })
    expect(invalidate).toHaveBeenCalledTimes(2)
  })
})
