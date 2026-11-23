import type { ReactNode } from "react"
import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import {
  bundleAgentIdsOf,
  formatBundleAgents,
  selectionOf,
  useCatalogHint,
  useCreateAgent,
  useCreateBundle,
  useCreateCustomAgent,
  useCreateMySkill,
  useCreateMyTool,
  useCreateSkill,
  useCreateTool,
  useSaveBundleChanges,
  useUpdateAgent,
} from "@/hooks/useBundleBuilder"
import type { ConfigBundleRead } from "@/types/Index"
import { server } from "../../server"

const BASE = "http://localhost:8000"

const baseBundle: ConfigBundleRead = {
  id: 10,
  user_id: 1,
  agent_id: 2,
  agent_profiles: [
    { id: 2, agent_name: "Architect", description: "d1" },
    { id: 3, agent_name: "Reviewer", description: "d2" },
  ],
  name: "Team Bundle",
  description: "Initial desc",
  skills: [{ id: 11, skill_name: "UML", description: "s" }],
  tools: [{ id: 21, tool_name: "GitHub", description: "t" }],
  knowledge_packs: [{ id: 31, name: "Docs", slug: "docs", domain_id: 1, description: "p", version: 1 }],
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper, invalidate }
}

describe("useBundleBuilder pure helpers", () => {
  it("extracts agent IDs and formats agent names for multi-agent and legacy bundles", () => {
    expect(bundleAgentIdsOf(baseBundle)).toEqual([2, 3])
    expect(formatBundleAgents(baseBundle)).toBe("Architect, Reviewer")

    const legacy: ConfigBundleRead = { ...baseBundle, agent_profiles: [], agent_id: 2 }
    expect(bundleAgentIdsOf(legacy)).toEqual([2])
    expect(
      formatBundleAgents(legacy, [{ id: 2, agent_name: "Architect", description: "d", skills: [], tools: [] }]),
    ).toBe("Architect")
    expect(formatBundleAgents(legacy, [])).toBe("#2")

    const empty: ConfigBundleRead = { ...baseBundle, agent_profiles: [], agent_id: null }
    expect(bundleAgentIdsOf(empty)).toEqual([])
    expect(formatBundleAgents(empty)).toBe("No profile")

    expect(selectionOf(baseBundle)).toEqual({
      agent_ids: [2, 3],
      skill_ids: [11],
      tool_ids: [21],
      knowledge_pack_ids: [31],
    })
  })
})

describe("useBundleBuilder mutations", () => {
  it("saves bundle changes by calling update, addItems, and removeItems only when needed", async () => {
    const calls: { op: string; body: unknown }[] = []
    server.use(
      mock.patch(`${BASE}/config-bundles/10`, async ({ request }) => {
        const body = await request.json()
        calls.push({ op: "update", body })
        return HttpResponse.json({ ...baseBundle, ...(body as object) })
      }),
      mock.post(`${BASE}/config-bundles/10/items`, async ({ request }) => {
        const body = await request.json()
        calls.push({ op: "add", body })
        return HttpResponse.json(baseBundle)
      }),
      mock.post(`${BASE}/config-bundles/10/items/remove`, async ({ request }) => {
        const body = await request.json()
        calls.push({ op: "remove", body })
        return HttpResponse.json(baseBundle)
      }),
    )

    const { wrapper } = createWrapper()
    const save = renderHook(() => useSaveBundleChanges(), { wrapper })

    await act(async () => {
      await save.result.current.mutateAsync({
        original: baseBundle,
        name: "Renamed Bundle",
        description: "Initial desc",
        selection: {
          agent_ids: [2, 4],
          skill_ids: [11, 12],
          tool_ids: [],
          knowledge_pack_ids: [31],
        },
      })
    })

    expect(calls).toEqual([
      { op: "update", body: { name: "Renamed Bundle", description: "Initial desc" } },
      {
        op: "add",
        body: { agent_ids: [4], skill_ids: [12], tool_ids: [], knowledge_pack_ids: [] },
      },
      {
        op: "remove",
        body: { agent_ids: [3], skill_ids: [], tool_ids: [21], knowledge_pack_ids: [] },
      },
    ])
  })

  it("executes catalog creation and hint mutations and invalidates catalog queries", async () => {
    server.use(
      mock.post(`${BASE}/catalog/hint`, () =>
        HttpResponse.json({
          agent_profile: null,
          skills: [],
          tools: [],
          knowledge_packs: [],
          reasoning: "ok",
        }),
      ),
      mock.post(`${BASE}/config-bundles`, () => HttpResponse.json(baseBundle)),
      mock.post(`${BASE}/agents`, () =>
        HttpResponse.json({ id: 1, agent_name: "A", description: "d", skills: [], tools: [] }),
      ),
      mock.put(`${BASE}/agents/1`, () =>
        HttpResponse.json({ id: 1, agent_name: "A", description: "u", skills: [], tools: [] }),
      ),
      mock.post(`${BASE}/skills`, () =>
        HttpResponse.json({ id: 1, skill_name: "S", description: "d", skill_selected_freq: 0 }),
      ),
      mock.post(`${BASE}/tools`, () =>
        HttpResponse.json({
          id: 1,
          tool_name: "T",
          description: "d",
          url: "https://x.io",
          auth_type: "none",
          auth_description: null,
          tool_selected_freq: 0,
        }),
      ),
      mock.post(`${BASE}/my/skills`, () =>
        HttpResponse.json({
          id: 2,
          skill_name: "MS",
          description: "d",
          content: "c",
          content_hash: "h",
          visibility: "private",
          archived_at: null,
          created_at: "2026-11-22T00:00:00Z",
          updated_at: "2026-11-22T00:00:00Z",
        }),
      ),
      mock.post(`${BASE}/my/tools`, () =>
        HttpResponse.json({
          tool: {
            id: 2,
            tool_name: "MT",
            description: "d",
            url: "https://x.io",
            auth_type: "none",
            auth_description: null,
            archived_at: null,
            created_at: "2026-11-22T00:00:00Z",
            updated_at: "2026-11-22T00:00:00Z",
          },
          warnings: [],
        }),
      ),
      mock.post(`${BASE}/agents/custom`, () =>
        HttpResponse.json({
          id: 99,
          name: "Custom",
          description: "d",
          agent_id: 1,
          skills: [],
          tools: [],
          knowledge_packs: [],
        }),
      ),
    )

    const { wrapper, invalidate } = createWrapper()

    const hint = renderHook(() => useCatalogHint(), { wrapper })
    const createBundle = renderHook(() => useCreateBundle(), { wrapper })
    const createAgent = renderHook(() => useCreateAgent(), { wrapper })
    const updateAgent = renderHook(() => useUpdateAgent(), { wrapper })
    const createSkill = renderHook(() => useCreateSkill(), { wrapper })
    const createTool = renderHook(() => useCreateTool(), { wrapper })
    const createMySkill = renderHook(() => useCreateMySkill(), { wrapper })
    const createMyTool = renderHook(() => useCreateMyTool(), { wrapper })
    const createCustomAgent = renderHook(() => useCreateCustomAgent(), { wrapper })

    await act(async () => {
      await hint.result.current.mutateAsync("build api")
      await createBundle.result.current.mutateAsync({
        agent_id: 2,
        name: "B",
        description: "d",
        skill_ids: [],
        tool_ids: [],
      })
      await createAgent.result.current.mutateAsync({
        name: "A",
        description: "d",
        skill_ids: [],
        tool_ids: [],
      })
      await updateAgent.result.current.mutateAsync({ id: 1, body: { description: "u" } })
      await createSkill.result.current.mutateAsync({
        skill_name: "S",
        description: "d",
        content: "c",
      })
      await createTool.result.current.mutateAsync({
        tool_name: "T",
        description: "d",
        url: "https://x.io",
      })
      await createMySkill.result.current.mutateAsync({
        skill_name: "MS",
        description: "d",
        content: "c",
      })
      await createMyTool.result.current.mutateAsync({
        tool_name: "MT",
        description: "d",
        url: "https://x.io",
      })
      await createCustomAgent.result.current.mutateAsync({ name: "Custom" })
    })

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["catalog", "agents"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["catalog", "skills"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["catalog", "tools"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["bundles"] })
  })
})
