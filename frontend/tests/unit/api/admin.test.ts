import { http as mock, HttpResponse } from "msw"
import { adminApi, adminUserContentApi } from "@/api"
import { server } from "../../server"

const BASE = "http://localhost:8000"

describe("adminApi", () => {
  it("fetches admins list", async () => {
    server.use(mock.get(`${BASE}/admin/admins`, () => HttpResponse.json([{ id: 1, username: "root" }])))

    const res = await adminApi.admins()
    expect(res).toEqual([{ id: 1, username: "root" }])
  })

  it("updates user role via PUT /admin/users/:id/role", async () => {
    let body: unknown
    server.use(
      mock.put(`${BASE}/admin/users/4/role`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 4, role: "admin" })
      }),
    )

    const res = await adminApi.setRole(4, { role: "admin" })
    expect(res).toMatchObject({ id: 4, role: "admin" })
    expect(body).toEqual({ role: "admin" })
  })

  it("fetches users with pagination params and single user by id", async () => {
    let query = ""
    server.use(
      mock.get(`${BASE}/admin/users`, ({ request }) => {
        query = new URL(request.url).search
        return HttpResponse.json([{ id: 2, username: "alice" }])
      }),
      mock.get(`${BASE}/admin/users/2`, () => HttpResponse.json({ id: 2, username: "alice" })),
    )

    const list = await adminApi.users({ limit: 50, offset: 10 })
    const single = await adminApi.user(2)

    expect(query).toBe("?limit=50&offset=10")
    expect(list).toHaveLength(1)
    expect(single).toMatchObject({ id: 2, username: "alice" })
  })

  it("sets token limit and resets token usage", async () => {
    let limitBody: unknown
    let resetCalled = false
    server.use(
      mock.put(`${BASE}/admin/users/3/token-limit`, async ({ request }) => {
        limitBody = await request.json()
        return HttpResponse.json({ id: 3, token_limit: 5000 })
      }),
      mock.post(`${BASE}/admin/users/3/reset-usage`, () => {
        resetCalled = true
        return HttpResponse.json({ id: 3, tokens_used: 0 })
      }),
    )

    const updated = await adminApi.setTokenLimit(3, { token_limit: 5000 })
    const reset = await adminApi.resetUsage(3)

    expect(limitBody).toEqual({ token_limit: 5000 })
    expect(updated).toMatchObject({ token_limit: 5000 })
    expect(resetCalled).toBe(true)
    expect(reset).toMatchObject({ tokens_used: 0 })
  })
})

describe("adminUserContentApi", () => {
  it("fetches user overview, skills, skill detail, and tools", async () => {
    let skillsQuery = ""
    let toolsQuery = ""
    server.use(
      mock.get(`${BASE}/admin/users/5/overview`, () =>
        HttpResponse.json({ user_id: 5, private_skills: 2, private_tools: 1, bundles: 3 }),
      ),
      mock.get(`${BASE}/admin/users/5/skills`, ({ request }) => {
        skillsQuery = new URL(request.url).search
        return HttpResponse.json([{ id: 10, skill_name: "Custom SQL" }])
      }),
      mock.get(`${BASE}/admin/users/5/skills/10`, () =>
        HttpResponse.json({ id: 10, skill_name: "Custom SQL", content: "# SQL" }),
      ),
      mock.get(`${BASE}/admin/users/5/tools`, ({ request }) => {
        toolsQuery = new URL(request.url).search
        return HttpResponse.json([{ id: 20, tool_name: "Custom MCP" }])
      }),
    )

    const overview = await adminUserContentApi.overview(5)
    const skills = await adminUserContentApi.skills(5, { include_archived: true, limit: 20 })
    const skill = await adminUserContentApi.skill(5, 10)
    const tools = await adminUserContentApi.tools(5, { include_archived: false })

    expect(overview).toMatchObject({ user_id: 5, private_skills: 2 })
    expect(skillsQuery).toBe("?include_archived=true&limit=20")
    expect(skills).toHaveLength(1)
    expect(skill).toMatchObject({ id: 10, content: "# SQL" })
    expect(toolsQuery).toBe("?include_archived=false")
    expect(tools).toHaveLength(1)
  })

  it("archives a user skill with a violation reason", async () => {
    let body: unknown
    server.use(
      mock.post(`${BASE}/admin/users/5/skills/10/archive`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 10, archived_at: "2026-11-22T10:00:00Z" })
      }),
    )

    const res = await adminUserContentApi.archiveSkill(5, 10, { reason: "Policy violation" })
    expect(body).toEqual({ reason: "Policy violation" })
    expect(res).toMatchObject({ id: 10, archived_at: "2026-11-22T10:00:00Z" })
  })
})
