import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import { useUserBundles } from "@/hooks/useAdminUserBundles"
import {
  useAdminUsers,
  useArchiveUserSkill,
  useResetUsage,
  useSetTokenLimit,
  useUserOverview,
  useUserSkillContent,
  useUserSkills,
  useUserTools,
} from "@/hooks/useAdminUsers"
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

describe("useAdminUsers and admin user content hooks", () => {
  it("loads admin users list, updates token limit, and resets usage", async () => {
    server.use(
      mock.get(`${BASE}/admin/users`, () =>
        HttpResponse.json([{ id: 1, username: "alice", token_limit: 1000, tokens_used: 200 }]),
      ),
      mock.put(`${BASE}/admin/users/1/token-limit`, async ({ request }) => {
        const body = (await request.json()) as { token_limit: number }
        return HttpResponse.json({ id: 1, username: "alice", token_limit: body.token_limit })
      }),
      mock.post(`${BASE}/admin/users/1/reset-usage`, () =>
        HttpResponse.json({ id: 1, username: "alice", tokens_used: 0 }),
      ),
    )

    const { wrapper, invalidate } = createWrapper()
    const usersHook = renderHook(() => useAdminUsers(), { wrapper })
    await waitFor(() => expect(usersHook.result.current.data).toHaveLength(1))

    const limitHook = renderHook(() => useSetTokenLimit(), { wrapper })
    await act(async () => {
      await limitHook.result.current.mutateAsync({ id: 1, tokenLimit: 5000 })
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["admin", "users"] })

    const resetHook = renderHook(() => useResetUsage(), { wrapper })
    await act(async () => {
      await resetHook.result.current.mutateAsync(1)
    })
    expect(invalidate).toHaveBeenCalledTimes(2)
  })

  it("loads user overview, skills, skill content, tools, bundles, and archives a skill", async () => {
    server.use(
      mock.get(`${BASE}/admin/users/7/overview`, () =>
        HttpResponse.json({ user_id: 7, private_skills: 1, private_tools: 1, bundles: 1 }),
      ),
      mock.get(`${BASE}/admin/users/7/skills`, () =>
        HttpResponse.json([{ id: 10, skill_name: "Private Skill" }]),
      ),
      mock.get(`${BASE}/admin/users/7/skills/10`, () =>
        HttpResponse.json({ id: 10, skill_name: "Private Skill", content: "# Content" }),
      ),
      mock.get(`${BASE}/admin/users/7/tools`, () =>
        HttpResponse.json([{ id: 20, tool_name: "Private Tool" }]),
      ),
      mock.get(`${BASE}/config-bundles`, ({ request }) => {
        const uid = new URL(request.url).searchParams.get("user_id")
        return HttpResponse.json([{ id: 30, user_id: Number(uid), name: "User Bundle" }])
      }),
      mock.post(`${BASE}/admin/users/7/skills/10/archive`, () =>
        HttpResponse.json({ id: 10, archived_at: "2026-11-22T12:00:00Z" }),
      ),
    )

    const { wrapper, invalidate } = createWrapper()

    const overview = renderHook(() => useUserOverview(7), { wrapper })
    const skills = renderHook(() => useUserSkills(7, false), { wrapper })
    const tools = renderHook(() => useUserTools(7, true), { wrapper })
    const bundles = renderHook(() => useUserBundles(7), { wrapper })
    const disabledSkill = renderHook(() => useUserSkillContent(7, 10, false), { wrapper })
    const enabledSkill = renderHook(() => useUserSkillContent(7, 10, true), { wrapper })

    await waitFor(() => expect(overview.result.current.data?.user_id).toBe(7))
    await waitFor(() => expect(skills.result.current.data).toHaveLength(1))
    await waitFor(() => expect(tools.result.current.data).toHaveLength(1))
    await waitFor(() => expect(bundles.result.current.data?.[0]?.user_id).toBe(7))
    expect(disabledSkill.result.current.fetchStatus).toBe("idle")
    await waitFor(() => expect(enabledSkill.result.current.data?.content).toBe("# Content"))

    const archive = renderHook(() => useArchiveUserSkill(7), { wrapper })
    await act(async () => {
      await archive.result.current.mutateAsync({ skillId: 10, reason: "Outdated" })
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["admin", "users", 7] })
  })
})
