import { http as mock, HttpResponse } from "msw"
import {
  agentsApi,
  catalogApi,
  domainsApi,
  knowledgePacksApi,
  skillsApi,
  toolsApi,
} from "@/api"
import { server } from "../../server"

const BASE = "http://localhost:8000"

describe("agentsApi", () => {
  it("lists, gets, creates, updates, archives, restores, and creates custom agents", async () => {
    const calls: string[] = []
    server.use(
      mock.get(`${BASE}/agents`, ({ request }) => {
        calls.push(`GET ${new URL(request.url).pathname}${new URL(request.url).search}`)
        return HttpResponse.json([{ id: 1, agent_name: "Architect" }])
      }),
      mock.get(`${BASE}/agents/1`, () => HttpResponse.json({ id: 1, agent_name: "Architect" })),
      mock.post(`${BASE}/agents`, async ({ request }) => {
        const body = (await request.json()) as { name: string }
        return HttpResponse.json({ id: 2, agent_name: body.name })
      }),
      mock.post(`${BASE}/agents/custom`, async ({ request }) => {
        const body = (await request.json()) as { name: string }
        return HttpResponse.json({ id: 99, name: body.name, agent_id: 1 })
      }),
      mock.put(`${BASE}/agents/1`, async ({ request }) => {
        const body = (await request.json()) as { description: string }
        return HttpResponse.json({ id: 1, description: body.description })
      }),
      mock.post(`${BASE}/agents/1/archive`, () => HttpResponse.json({ id: 1 })),
      mock.post(`${BASE}/agents/1/restore`, () => HttpResponse.json({ id: 1 })),
    )

    expect(await agentsApi.list({ limit: 10 })).toHaveLength(1)
    expect(calls[0]).toBe("GET /agents?limit=10")
    expect(await agentsApi.get(1)).toMatchObject({ id: 1 })
    expect(
      await agentsApi.create({ name: "Coder", description: "d", skill_ids: [], tool_ids: [] }),
    ).toMatchObject({ agent_name: "Coder" })
    expect(await agentsApi.createCustom({ name: "My Agent" })).toMatchObject({ id: 99 })
    expect(await agentsApi.update(1, { description: "updated" })).toMatchObject({
      description: "updated",
    })
    expect(await agentsApi.archive(1)).toMatchObject({ id: 1 })
    expect(await agentsApi.restore(1)).toMatchObject({ id: 1 })
  })
})

describe("skillsApi and toolsApi", () => {
  it("handles CRUD, domain filtering, archive/restore, and markdown download for skills", async () => {
    server.use(
      mock.get(`${BASE}/skills`, () => HttpResponse.json([{ id: 1, skill_name: "Docker" }])),
      mock.get(`${BASE}/skills/by-domain/3`, () =>
        HttpResponse.json([{ id: 2, skill_name: "K8s" }]),
      ),
      mock.get(`${BASE}/skills/1`, () => HttpResponse.json({ id: 1, skill_name: "Docker" })),
      mock.get(`${BASE}/skills/1/download`, () =>
        new HttpResponse("# Docker", {
          headers: { "Content-Disposition": 'attachment; filename="SKILL.md"' },
        }),
      ),
      mock.post(`${BASE}/skills`, async ({ request }) => HttpResponse.json(await request.json())),
      mock.put(`${BASE}/skills/1`, async ({ request }) =>
        HttpResponse.json({ id: 1, ...(await request.json() as object) }),
      ),
      mock.post(`${BASE}/skills/1/archive`, () => HttpResponse.json({ id: 1 })),
      mock.post(`${BASE}/skills/1/restore`, () => HttpResponse.json({ id: 1 })),
    )

    expect(await skillsApi.list()).toHaveLength(1)
    expect(await skillsApi.byDomain(3, { limit: 5 })).toEqual([{ id: 2, skill_name: "K8s" }])
    expect(await skillsApi.get(1)).toMatchObject({ id: 1 })
    const file = await skillsApi.downloadMarkdown(1)
    expect(file.filename).toBe("SKILL.md")
    expect(
      await skillsApi.create({ skill_name: "S", description: "d", content: "c" }),
    ).toMatchObject({ skill_name: "S" })
    expect(await skillsApi.update(1, { description: "new" })).toMatchObject({ description: "new" })
    expect(await skillsApi.archive(1)).toMatchObject({ id: 1 })
    expect(await skillsApi.restore(1)).toMatchObject({ id: 1 })
  })

  it("handles CRUD, domain filtering, and archive/restore for tools", async () => {
    server.use(
      mock.get(`${BASE}/tools`, () => HttpResponse.json([{ id: 1, tool_name: "GitHub" }])),
      mock.get(`${BASE}/tools/by-domain/4`, () =>
        HttpResponse.json([{ id: 2, tool_name: "GitLab" }]),
      ),
      mock.get(`${BASE}/tools/1`, () => HttpResponse.json({ id: 1, tool_name: "GitHub" })),
      mock.post(`${BASE}/tools`, async ({ request }) => HttpResponse.json(await request.json())),
      mock.put(`${BASE}/tools/1`, async ({ request }) =>
        HttpResponse.json({ id: 1, ...(await request.json() as object) }),
      ),
      mock.post(`${BASE}/tools/1/archive`, () => HttpResponse.json({ id: 1 })),
      mock.post(`${BASE}/tools/1/restore`, () => HttpResponse.json({ id: 1 })),
    )

    expect(await toolsApi.list()).toHaveLength(1)
    expect(await toolsApi.byDomain(4)).toEqual([{ id: 2, tool_name: "GitLab" }])
    expect(await toolsApi.get(1)).toMatchObject({ id: 1 })
    expect(
      await toolsApi.create({ tool_name: "T", description: "d", url: "https://mcp.local" }),
    ).toMatchObject({ tool_name: "T" })
    expect(await toolsApi.update(1, { description: "u" })).toMatchObject({ description: "u" })
    expect(await toolsApi.archive(1)).toMatchObject({ id: 1 })
    expect(await toolsApi.restore(1)).toMatchObject({ id: 1 })
  })
})

describe("domainsApi, knowledgePacksApi, and catalogApi", () => {
  it("calls domain endpoints", async () => {
    server.use(
      mock.get(`${BASE}/domains`, () => HttpResponse.json([{ id: 1, slug: "backend" }])),
      mock.get(`${BASE}/domains/roots`, () => HttpResponse.json([{ id: 1, slug: "backend" }])),
      mock.get(`${BASE}/domains/1`, () => HttpResponse.json({ id: 1, slug: "backend" })),
      mock.post(`${BASE}/domains`, async ({ request }) => HttpResponse.json(await request.json())),
    )

    expect(await domainsApi.list()).toHaveLength(1)
    expect(await domainsApi.roots()).toHaveLength(1)
    expect(await domainsApi.get(1)).toMatchObject({ slug: "backend" })
    expect(
      await domainsApi.create({ slug: "ai", name: "AI", description: "AI domain" }),
    ).toMatchObject({ slug: "ai" })
  })

  it("calls knowledgePacks endpoints and encodes slug", async () => {
    let requestedPath = ""
    server.use(
      mock.get(`${BASE}/knowledge-packs`, () => HttpResponse.json([{ id: 1, slug: "pack-1" }])),
      mock.get(`${BASE}/knowledge-packs/by-domain/2`, () =>
        HttpResponse.json([{ id: 2, slug: "pack-2" }]),
      ),
      mock.get(`${BASE}/knowledge-packs/:slug`, ({ request }) => {
        requestedPath = new URL(request.url).pathname
        return HttpResponse.json({ id: 3, slug: "a/b" })
      }),
      mock.post(`${BASE}/knowledge-packs`, async ({ request }) =>
        HttpResponse.json(await request.json()),
      ),
      mock.post(`${BASE}/knowledge-packs/1/archive`, () => HttpResponse.json({ id: 1 })),
      mock.post(`${BASE}/knowledge-packs/1/restore`, () => HttpResponse.json({ id: 1 })),
    )

    expect(await knowledgePacksApi.list()).toHaveLength(1)
    expect(await knowledgePacksApi.byDomain(2)).toHaveLength(1)
    await knowledgePacksApi.bySlug("a/b")
    expect(requestedPath).toBe("/knowledge-packs/a%2Fb")
    expect(
      await knowledgePacksApi.create({ name: "P", slug: "p", domain_id: 1, description: "d" }),
    ).toMatchObject({ slug: "p" })
    expect(await knowledgePacksApi.archive(1)).toMatchObject({ id: 1 })
    expect(await knowledgePacksApi.restore(1)).toMatchObject({ id: 1 })
  })

  it("posts intent to /catalog/hint", async () => {
    server.use(
      mock.post(`${BASE}/catalog/hint`, async ({ request }) => {
        const body = (await request.json()) as { intent: string }
        return HttpResponse.json({
          agent_profile: null,
          skills: [],
          tools: [],
          knowledge_packs: [],
          reasoning: `Hint for ${body.intent}`,
        })
      }),
    )

    const res = await catalogApi.hint({ intent: "docker" })
    expect(res.reasoning).toBe("Hint for docker")
  })
})
