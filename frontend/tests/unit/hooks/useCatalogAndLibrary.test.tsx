import type { ReactNode } from "react"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import { useAgents, usePacks, useSkills, useTools } from "@/hooks/useCatalog"
import { useMySkills, useMyTools } from "@/hooks/useMyLibrary"
import { server } from "../../server"

const BASE = "http://localhost:8000"

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe("useCatalog and useMyLibrary hooks", () => {
  it("loads catalog agents, skills, tools, knowledge packs, and user's private library", async () => {
    server.use(
      mock.get(`${BASE}/agents`, () => HttpResponse.json([{ id: 1, agent_name: "Architect" }])),
      mock.get(`${BASE}/skills`, () => HttpResponse.json([{ id: 2, skill_name: "Docker" }])),
      mock.get(`${BASE}/tools`, () => HttpResponse.json([{ id: 3, tool_name: "GitHub" }])),
      mock.get(`${BASE}/knowledge-packs`, () => HttpResponse.json([{ id: 4, slug: "docs" }])),
      mock.get(`${BASE}/my/skills`, () => HttpResponse.json([{ id: 5, skill_name: "My Skill" }])),
      mock.get(`${BASE}/my/tools`, () => HttpResponse.json([{ id: 6, tool_name: "My Tool" }])),
    )

    const wrapper = createWrapper()
    const agents = renderHook(() => useAgents(), { wrapper })
    const skills = renderHook(() => useSkills(), { wrapper })
    const tools = renderHook(() => useTools(), { wrapper })
    const packs = renderHook(() => usePacks(), { wrapper })
    const mySkills = renderHook(() => useMySkills(), { wrapper })
    const myTools = renderHook(() => useMyTools(), { wrapper })

    await waitFor(() => expect(agents.result.current.data).toMatchObject([{ id: 1 }]))
    await waitFor(() => expect(skills.result.current.data).toMatchObject([{ id: 2 }]))
    await waitFor(() => expect(tools.result.current.data).toMatchObject([{ id: 3 }]))
    await waitFor(() => expect(packs.result.current.data).toMatchObject([{ id: 4 }]))
    await waitFor(() => expect(mySkills.result.current.data).toMatchObject([{ id: 5 }]))
    await waitFor(() => expect(myTools.result.current.data).toMatchObject([{ id: 6 }]))
  })
})
