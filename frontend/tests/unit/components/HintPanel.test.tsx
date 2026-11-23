import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import { HintPanel } from "@/components/builder/HintPanel"
import type { HintResponse, MySkillRead } from "@/types/Index"
import { server } from "../../server"

const BASE = "http://localhost:8000"

const hint: HintResponse = {
  agent_profile: null,
  skills: [],
  tools: [],
  knowledge_packs: [],
  reasoning: "Docker-related task.",
  gaps: [
    { kind: "skill", name: "Docker review", description: "Reviews Docker setups", reason: "No skill covers Dockerfiles" },
    { kind: "tool", name: "Grafana", description: "Dashboards", reason: "Needed for metrics" },
    { kind: "pack", name: "SRE handbook", description: "Runbooks", reason: "No ops knowledge" },
  ],
}

const draftResult = {
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
  skill_name: "Docker review v2",
  description: "Reviews Docker setups",
  content_hash: "h",
  visibility: "private",
  archived_at: null,
  content: draftResult.content,
  created_at: "2026-10-12T10:00:00Z",
  updated_at: "2026-10-12T10:00:00Z",
}

// stored job_id persists across tests unless cleared
beforeEach(() => sessionStorage.clear())

function renderPanel(props: Partial<Parameters<typeof HintPanel>[0]> = {}) {
  const onApply = vi.fn()
  const onSkillSaved = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <HintPanel onApply={onApply} onSkillSaved={onSkillSaved} {...props} />
    </QueryClientProvider>,
  )
  return { onApply, onSkillSaved, user: userEvent.setup() }
}

async function askHint(user: ReturnType<typeof userEvent.setup>, response: HintResponse = hint) {
  server.use(mock.post(`${BASE}/catalog/hint`, () => HttpResponse.json(response)))
  await user.type(screen.getByLabelText("What should the agent do?"), "review docker")
  await user.click(screen.getByRole("button", { name: "Suggest a setup" }))
  await screen.findByText(/Docker-related task/)
}

describe('HintPanel: "Not in the catalog" section', () => {
  it("is not shown when there are no gaps", async () => {
    const { user } = renderPanel()

    await askHint(user, { ...hint, gaps: [] })

    expect(screen.queryByText("Not in the catalog")).not.toBeInTheDocument()
  })

  it("does not crash if backend omits gaps", async () => {
    const { user } = renderPanel()
    const { gaps: _gaps, ...withoutGaps } = hint

    await askHint(user, withoutGaps)

    expect(screen.queryByText("Not in the catalog")).not.toBeInTheDocument()
  })

  it("shows a button for skill gaps and admin text for tool and pack gaps", async () => {
    const { user } = renderPanel()

    await askHint(user)

    expect(screen.getByText("Not in the catalog")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Create draft: Docker review" })).toBeEnabled()
    expect(screen.queryByRole("button", { name: /Create draft: Grafana/ })).not.toBeInTheDocument()
    expect(screen.getAllByText("Needs an admin to add it.")).toHaveLength(2)
  })
})

describe("HintPanel: skill draft", () => {
  it("flows from gap to saved skill", async () => {
    const bodies: unknown[] = []
    const confirmBodies: unknown[] = []
    server.use(
      mock.post(`${BASE}/my/skills/drafts`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({ job_id: 9, status: "pending" }, { status: 202 })
      }),
      mock.get(`${BASE}/my/skills/drafts/9`, () =>
        HttpResponse.json({ job_id: 9, status: "done", error: null, draft: draftResult }),
      ),
      mock.post(`${BASE}/my/skills/drafts/9/confirm`, async ({ request }) => {
        confirmBodies.push(await request.json())
        return HttpResponse.json(savedSkill, { status: 201 })
      }),
    )
    const { user, onSkillSaved } = renderPanel()
    await askHint(user)

    await user.type(screen.getByLabelText("Source text for the draft"), "Use official docs")
    await user.click(screen.getByRole("button", { name: "Create draft: Docker review" }))

    // draft is ready: displays unverified badge and warning
    const card = await screen.findByRole("region", { name: "Skill draft" })
    expect(within(card).getByText("Unverified")).toBeInTheDocument()
    expect(within(card).getByText("Verify image names")).toBeInTheDocument()
    expect(bodies).toEqual([
      { intent: "Docker review: Reviews Docker setups", source_text: "Use official docs" },
    ])
    // while a draft is open, another draft cannot be requested
    expect(screen.getByRole("button", { name: "Create draft: Docker review" })).toBeDisabled()

    // user edits the name and saves
    const name = within(card).getByLabelText("Skill name")
    await user.clear(name)
    await user.type(name, "Docker review v2")
    await user.click(within(card).getByRole("button", { name: "Save as my skill" }))

    expect(await within(card).findByText(/Saved "Docker review v2" as your private skill/)).toBeInTheDocument()
    expect(confirmBodies).toEqual([
      { skill_name: "Docker review v2", description: "Reviews Docker setups", content: draftResult.content },
    ])
    expect(onSkillSaved).toHaveBeenCalledWith(savedSkill)
  })

  it("passes config_bundle_id when editing a bundle and explains it", async () => {
    const bodies: unknown[] = []
    server.use(
      mock.post(`${BASE}/my/skills/drafts`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({ job_id: 9, status: "pending" }, { status: 202 })
      }),
      mock.get(`${BASE}/my/skills/drafts/9`, () =>
        HttpResponse.json({
          job_id: 9,
          status: "done",
          error: null,
          draft: { ...draftResult, grounded: true, sources: ["handbook.md"], warnings: [] },
        }),
      ),
    )
    const { user } = renderPanel({ configBundleId: 5 })
    await askHint(user)
    expect(screen.getByText(/checked against this bundle's knowledge/)).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Create draft: Docker review" }))

    const card = await screen.findByRole("region", { name: "Skill draft" })
    expect(within(card).getByText("Grounded in knowledge")).toBeInTheDocument()
    expect(within(card).getByText("handbook.md")).toBeInTheDocument()
    expect(bodies).toEqual([{ intent: "Docker review: Reviews Docker setups", config_bundle_id: 5 }])
  })

  it("shows a human-readable message when the queue is unavailable (503)", async () => {
    server.use(
      mock.post(`${BASE}/my/skills/drafts`, () =>
        HttpResponse.json({ detail: "Queue unavailable" }, { status: 503 }),
      ),
    )
    const { user } = renderPanel()
    await askHint(user)

    await user.click(screen.getByRole("button", { name: "Create draft: Docker review" }))

    expect(await screen.findByText(/generation queue is temporarily unavailable/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Create draft: Docker review" })).toBeEnabled()
  })

  it("Read toggle shows plain text for review without editing", async () => {
    server.use(
      mock.post(`${BASE}/my/skills/drafts`, () =>
        HttpResponse.json({ job_id: 9, status: "pending" }, { status: 202 }),
      ),
      mock.get(`${BASE}/my/skills/drafts/9`, () =>
        HttpResponse.json({ job_id: 9, status: "done", error: null, draft: draftResult }),
      ),
    )
    const { user } = renderPanel()
    await askHint(user)
    await user.click(screen.getByRole("button", { name: "Create draft: Docker review" }))
    const card = await screen.findByRole("region", { name: "Skill draft" })

    await user.click(within(card).getByRole("button", { name: "Read" }))

    expect(within(card).getByLabelText("Draft content")).toHaveTextContent("Check base images.")
    expect(within(card).queryByRole("textbox", { name: "Content" })).not.toBeInTheDocument()
  })
})
