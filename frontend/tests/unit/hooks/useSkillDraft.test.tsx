import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import { useSkillDraft } from "@/hooks/useSkillDraft"
import { readStoredJob, storeJob } from "@/lib/skillDraft"
import type { MySkillRead, SkillDraftResult, SkillDraftStatus } from "@/types/Index"
import { server } from "../../server"

const BASE = "http://localhost:8000"

const result: SkillDraftResult = {
  skill_name: "Docker review",
  description: "Reviews Docker setups",
  content: "# Docker\nCheck base images.",
  grounded: false,
  sources: [],
  used_packs: [],
  warnings: ["Verify image names"],
}

const savedSkill: MySkillRead = {
  id: 77,
  skill_name: "Docker review",
  description: "Reviews Docker setups",
  content_hash: "h",
  visibility: "private",
  archived_at: null,
  content: result.content,
  created_at: "2026-10-12T10:00:00Z",
  updated_at: "2026-10-12T10:00:00Z",
}

function status(s: SkillDraftStatus["status"], extra: Partial<SkillDraftStatus> = {}): SkillDraftStatus {
  return { job_id: 9, status: s, error: null, draft: null, ...extra }
}

/** Serves statuses in order; repeats the last one. Counts requests. */
function serveStatuses(jobId: number, statuses: SkillDraftStatus[]) {
  const calls = { count: 0 }
  server.use(
    mock.get(`${BASE}/my/skills/drafts/${jobId}`, () => {
      const item = statuses[Math.min(calls.count, statuses.length - 1)]
      calls.count += 1
      return HttpResponse.json(item)
    }),
  )
  return calls
}

function serveRequest(jobId = 9) {
  const bodies: unknown[] = []
  server.use(
    mock.post(`${BASE}/my/skills/drafts`, async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json({ job_id: jobId, status: "pending" }, { status: 202 })
    }),
  )
  return bodies
}

function setup(options: Parameters<typeof useSkillDraft>[0] = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const view = renderHook(() => useSkillDraft({ pollDelay: () => 100, ...options }), { wrapper })
  return { ...view, invalidate }
}

beforeEach(() => sessionStorage.clear())

describe("useSkillDraft: generation", () => {
  it("transitions through queue and generation to a ready draft", async () => {
    const bodies = serveRequest()
    serveStatuses(9, [status("pending"), status("running"), status("done", { draft: result })])
    const { result: hook } = setup()

    act(() => hook.current.requestDraft({ intent: "docker: review", sourceText: "  my notes " }))

    await waitFor(() => expect(hook.current.phase).toMatchObject({ name: "waiting", label: "Queued" }))
    await waitFor(() => expect(hook.current.phase).toMatchObject({ name: "waiting", label: "Generating" }))
    await waitFor(() => expect(hook.current.phase).toMatchObject({ name: "ready", jobId: 9 }))

    expect(bodies).toEqual([{ intent: "docker: review", source_text: "my notes" }])
    expect(readStoredJob()).toBe(9)
  })

  it("includes config_bundle_id when a bundle is active", async () => {
    const bodies = serveRequest()
    serveStatuses(9, [status("pending")])
    const { result: hook } = setup({ configBundleId: 7 })

    act(() => hook.current.requestDraft({ intent: "docker: review" }))
    await waitFor(() => expect(bodies).toHaveLength(1))

    expect(bodies[0]).toEqual({ intent: "docker: review", config_bundle_id: 7 })
  })

  it("stops polling after done", async () => {
    serveRequest()
    const calls = serveStatuses(9, [status("done", { draft: result })])
    const { result: hook } = setup()

    act(() => hook.current.requestDraft({ intent: "x" }))
    await waitFor(() => expect(hook.current.phase.name).toBe("ready"))
    await new Promise((resolve) => setTimeout(resolve, 350))

    expect(calls.count).toBe(1)
  })

  it("shows the generation error from failed status", async () => {
    serveRequest()
    serveStatuses(9, [status("failed", { error: "LLM unavailable" })])
    const { result: hook } = setup()

    act(() => hook.current.requestDraft({ intent: "x" }))

    await waitFor(() => expect(hook.current.phase).toEqual({ name: "failed", message: "LLM unavailable" }))
  })

  it("treats an empty draft with done status as a failure", async () => {
    serveRequest()
    serveStatuses(9, [status("done", { draft: null })])
    const { result: hook } = setup()

    act(() => hook.current.requestDraft({ intent: "x" }))

    await waitFor(() => expect(hook.current.phase.name).toBe("failed"))
  })

  it("enters error phase (not failed) on network failure during polling", async () => {
    serveRequest()
    server.use(mock.get(`${BASE}/my/skills/drafts/9`, () => HttpResponse.error()))
    const { result: hook } = setup()

    act(() => hook.current.requestDraft({ intent: "x" }))

    await waitFor(() => expect(hook.current.phase).toEqual({ name: "error", message: "Can't reach the server." }))
  })
})

describe("useSkillDraft: request errors", () => {
  it.each([
    [429, { "Retry-After": "30" }, "Too many requests. Try again in 30s."],
    [409, {}, "Can't create this skill: you've reached the limit of 50 custom skills, or a skill with this name already exists."],
    [503, {}, "The generation queue is temporarily unavailable. Try again in a minute."],
  ])("maps status %i to a human-readable message", async (code, headers, expected) => {
    server.use(
      mock.post(`${BASE}/my/skills/drafts`, () =>
        HttpResponse.json({ detail: "x" }, { status: code, headers }),
      ),
    )
    const { result: hook } = setup()

    act(() => hook.current.requestDraft({ intent: "x" }))

    await waitFor(() => expect(hook.current.requestError).toBe(expected))
    expect(hook.current.phase.name).toBe("idle")
    expect(readStoredJob()).toBeNull()
  })
})

describe("useSkillDraft: saving", () => {
  async function readyHook(onSaved = vi.fn()) {
    serveRequest()
    serveStatuses(9, [status("done", { draft: result })])
    const view = setup({ onSaved })
    act(() => view.result.current.requestDraft({ intent: "x" }))
    await waitFor(() => expect(view.result.current.phase.name).toBe("ready"))
    return { ...view, onSaved }
  }

  it("saves the draft, invokes onSaved, and invalidates skills query", async () => {
    const bodies: unknown[] = []
    server.use(
      mock.post(`${BASE}/my/skills/drafts/9/confirm`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(savedSkill, { status: 201 })
      }),
    )
    const { result: hook, onSaved, invalidate } = await readyHook()

    act(() => hook.current.save({ skill_name: "Docker review v2", description: "d", content: "c" }))

    await waitFor(() => expect(hook.current.phase).toEqual({ name: "saved", skill: savedSkill }))
    expect(bodies).toEqual([{ skill_name: "Docker review v2", description: "d", content: "c" }])
    expect(onSaved).toHaveBeenCalledWith(savedSkill)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["catalog", "skills"] })
    expect(readStoredJob()).toBeNull()
  })

  it("treats 409 on confirm as already saved without error", async () => {
    server.use(
      mock.post(`${BASE}/my/skills/drafts/9/confirm`, () =>
        HttpResponse.json({ detail: "already confirmed" }, { status: 409 }),
      ),
    )
    const { result: hook, onSaved } = await readyHook()

    act(() => hook.current.save({ skill_name: "n", description: "d", content: "c" }))

    await waitFor(() => expect(hook.current.phase).toEqual({ name: "saved", skill: null }))
    expect(hook.current.saveError).toBeNull()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it("keeps the draft and displays an error message on other save failures", async () => {
    server.use(
      mock.post(`${BASE}/my/skills/drafts/9/confirm`, () =>
        HttpResponse.json({ detail: "Draft expired" }, { status: 400 }),
      ),
    )
    const { result: hook } = await readyHook()

    act(() => hook.current.save({ skill_name: "n", description: "d", content: "c" }))

    await waitFor(() => expect(hook.current.saveError).toBe("Draft expired"))
    expect(hook.current.phase.name).toBe("ready")
  })

  it("discards locally: clears state and sessionStorage", async () => {
    const { result: hook } = await readyHook()
    expect(readStoredJob()).toBe(9)

    act(() => hook.current.discard())

    expect(hook.current.phase.name).toBe("idle")
    expect(readStoredJob()).toBeNull()
  })
})

describe("useSkillDraft: recovery after page reload", () => {
  it("picks up the stored job and displays the ready draft", async () => {
    storeJob(9)
    serveStatuses(9, [status("done", { draft: result })])

    const { result: hook } = setup()

    expect(hook.current.phase).toMatchObject({ name: "waiting", label: "Queued" })
    await waitFor(() => expect(hook.current.phase).toMatchObject({ name: "ready", jobId: 9 }))
  })

  it("silently clears a job that no longer exists (404)", async () => {
    storeJob(9)
    server.use(
      mock.get(`${BASE}/my/skills/drafts/9`, () =>
        HttpResponse.json({ detail: "Job not found" }, { status: 404 }),
      ),
    )

    const { result: hook } = setup()

    await waitFor(() => expect(hook.current.phase.name).toBe("idle"))
    expect(readStoredJob()).toBeNull()
  })
})
