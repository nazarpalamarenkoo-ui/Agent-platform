import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import { MyBundles } from "@/components/builder/MyBundles"
import type { ConfigBundleRead, SkillRead } from "@/types/Index"
import { server } from "../../server"

const BASE = "http://localhost:8000"

const bundle: ConfigBundleRead = {
  id: 7,
  user_id: 1,
  agent_id: 3,
  name: "Infra helper",
  description: "Docker and CI",
  skills: [
    { id: 1, skill_name: "Planner", description: "plans" },
    { id: 2, skill_name: "My docker skill", description: "docker" },
  ],
  tools: [],
  knowledge_packs: [],
}

const skills: SkillRead[] = [
  { id: 1, skill_name: "Planner", description: "plans", skill_selected_freq: 3, visibility: "global" },
  { id: 2, skill_name: "My docker skill", description: "docker", skill_selected_freq: 0, visibility: "private" },
]

const originalCreate = URL.createObjectURL
const originalRevoke = URL.revokeObjectURL
let saved: string[]

beforeEach(() => {
  saved = []
  URL.createObjectURL = vi.fn(() => "blob:fake")
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    saved.push(this.download)
  })
  server.use(
    mock.get(`${BASE}/config-bundles`, () => HttpResponse.json([bundle])),
    mock.get(`${BASE}/skills`, () => HttpResponse.json(skills)),
  )
})

afterEach(() => {
  URL.createObjectURL = originalCreate
  URL.revokeObjectURL = originalRevoke
  vi.restoreAllMocks()
})

function renderBundles() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MyBundles agents={[]} activeId={null} deleting={false} onEdit={vi.fn()} onDelete={vi.fn()} />
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

describe("MyBundles: file downloads", () => {
  it("lists private skills with a download button and hides global skills", async () => {
    renderBundles()

    const heading = await screen.findByText("Private skills")
    const list = heading.parentElement as HTMLElement

    expect(within(list).getByText("My docker skill")).toBeInTheDocument()
    expect(within(list).queryByText("Planner")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Download SKILL.md: My docker skill" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Download SKILL.md: Planner/ })).not.toBeInTheDocument()
  })

  it("downloads bundle .zip using the filename from Content-Disposition", async () => {
    server.use(
      mock.get(`${BASE}/config-bundles/7/export`, () =>
        new HttpResponse("zip", {
          headers: { "Content-Disposition": 'attachment; filename="infra-helper-v3.zip"' },
        }),
      ),
    )
    const user = renderBundles()

    await user.click(await screen.findByRole("button", { name: "Download .zip" }))

    await vi.waitFor(() => expect(saved).toEqual(["infra-helper-v3.zip"]))
  })

  it("uses the fallback filename when the server omits Content-Disposition", async () => {
    server.use(mock.get(`${BASE}/config-bundles/7/export`, () => new HttpResponse("zip")))
    const user = renderBundles()

    await user.click(await screen.findByRole("button", { name: "Download .zip" }))

    await vi.waitFor(() => expect(saved).toEqual(["bundle-7.zip"]))
  })

  it("downloads SKILL.md for a private skill", async () => {
    server.use(
      mock.get(`${BASE}/my/skills/2/download`, () =>
        new HttpResponse("# skill", {
          headers: { "Content-Disposition": 'attachment; filename="SKILL.md"' },
        }),
      ),
    )
    const user = renderBundles()

    await user.click(await screen.findByRole("button", { name: "Download SKILL.md: My docker skill" }))

    await vi.waitFor(() => expect(saved).toEqual(["SKILL.md"]))
  })

  it("shows an error message on 404 instead of failing silently", async () => {
    server.use(
      mock.get(`${BASE}/config-bundles/7/export`, () =>
        HttpResponse.json({ detail: "Config bundle not found" }, { status: 404 }),
      ),
    )
    const user = renderBundles()

    await user.click(await screen.findByRole("button", { name: "Download .zip" }))

    expect(await screen.findByText("Nothing to download: it no longer exists.")).toBeInTheDocument()
    expect(saved).toEqual([])
  })
})
