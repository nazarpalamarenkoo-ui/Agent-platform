import { http as mock, HttpResponse } from "msw"
import {
  authApi,
  configBundlesApi,
  deviceApi,
  knowledgeApi,
  mySkillsApi,
  myToolsApi,
  notificationsApi,
  usersApi,
} from "@/api"
import { setToken } from "@/auth/session"
import { server } from "../../server"

const BASE = "http://localhost:8000"

describe("authApi and usersApi", () => {
  it("sends public auth requests without Authorization header", async () => {
    setToken("should-not-be-sent")
    const seenHeaders: (string | null)[] = []
    server.use(
      mock.post(`${BASE}/auth/login`, ({ request }) => {
        seenHeaders.push(request.headers.get("authorization"))
        return HttpResponse.json({ access_token: "jwt", token_type: "bearer" })
      }),
      mock.post(`${BASE}/auth/signup`, ({ request }) => {
        seenHeaders.push(request.headers.get("authorization"))
        return HttpResponse.json({ detail: "Email has been sent" })
      }),
      mock.post(`${BASE}/auth/signup-confirmation`, ({ request }) => {
        seenHeaders.push(request.headers.get("authorization"))
        return HttpResponse.json({ access_token: "jwt", token_type: "bearer" })
      }),
      mock.post(`${BASE}/auth/password-recovery`, ({ request }) => {
        seenHeaders.push(request.headers.get("authorization"))
        return HttpResponse.json({ detail: "Email has been sent" })
      }),
      mock.patch(`${BASE}/auth/reset-password`, ({ request }) => {
        seenHeaders.push(request.headers.get("authorization"))
        return HttpResponse.json({ detail: "Password updated successfully" })
      }),
    )

    await authApi.login({ email: "a@b.c", password: "pw" })
    await authApi.signup({ email: "a@b.c", password: "pw", username: "a" })
    await authApi.confirmSignup("tok1")
    await authApi.recoverPassword("a@b.c")
    await authApi.resetPassword({ token: "tok2", new_password: "newpw" })

    expect(seenHeaders).toEqual([null, null, null, null, null])
  })

  it("calls usersApi endpoints for profile, update, password change, and deletion", async () => {
    server.use(
      mock.get(`${BASE}/users/me`, () => HttpResponse.json({ id: 1, username: "me" })),
      mock.get(`${BASE}/users/2`, () => HttpResponse.json({ id: 2, username: "other" })),
      mock.patch(`${BASE}/users/1`, async ({ request }) =>
        HttpResponse.json({ id: 1, ...(await request.json() as object) }),
      ),
      mock.post(`${BASE}/users/1/change-password`, () => new HttpResponse(null, { status: 204 })),
      mock.delete(`${BASE}/users/1`, () => new HttpResponse(null, { status: 204 })),
    )

    expect(await usersApi.me()).toMatchObject({ username: "me" })
    expect(await usersApi.get(2)).toMatchObject({ username: "other" })
    expect(await usersApi.update(1, { username: "new-me" })).toMatchObject({ username: "new-me" })
    await expect(
      usersApi.changePassword(1, { old_password: "old", new_password: "new" }),
    ).resolves.toBeUndefined()
    await expect(usersApi.remove(1)).resolves.toBeUndefined()
  })
})

describe("mySkillsApi and myToolsApi", () => {
  it("calls private skill endpoints and draft endpoints", async () => {
    server.use(
      mock.get(`${BASE}/my/skills`, () => HttpResponse.json([{ id: 1, skill_name: "S1" }])),
      mock.get(`${BASE}/my/skills/1`, () => HttpResponse.json({ id: 1, skill_name: "S1" })),
      mock.post(`${BASE}/my/skills`, async ({ request }) => HttpResponse.json(await request.json())),
      mock.post(`${BASE}/my/skills/import`, () =>
        HttpResponse.json({ id: 2, skill_name: "Imported" }),
      ),
      mock.put(`${BASE}/my/skills/1`, async ({ request }) =>
        HttpResponse.json({ id: 1, ...(await request.json() as object) }),
      ),
      mock.post(`${BASE}/my/skills/1/archive`, () => HttpResponse.json({ id: 1 })),
      mock.post(`${BASE}/my/skills/1/restore`, () => HttpResponse.json({ id: 1 })),
      mock.get(`${BASE}/my/skills/1/download`, () => new HttpResponse("# md")),
      mock.post(`${BASE}/my/skills/drafts`, () =>
        HttpResponse.json({ job_id: 11, status: "pending" }),
      ),
      mock.get(`${BASE}/my/skills/drafts/11`, () =>
        HttpResponse.json({ job_id: 11, status: "done", error: null, draft: null }),
      ),
      mock.post(`${BASE}/my/skills/drafts/11/confirm`, () =>
        HttpResponse.json({ id: 3, skill_name: "Confirmed" }),
      ),
    )

    expect(await mySkillsApi.list()).toHaveLength(1)
    expect(await mySkillsApi.get(1)).toMatchObject({ id: 1 })
    expect(
      await mySkillsApi.create({ skill_name: "New", description: "d", content: "c" }),
    ).toMatchObject({ skill_name: "New" })
    expect(await mySkillsApi.importMarkdown({ markdown: "# Skill" })).toMatchObject({ id: 2 })
    expect(await mySkillsApi.update(1, { description: "u" })).toMatchObject({ description: "u" })
    expect(await mySkillsApi.archive(1)).toMatchObject({ id: 1 })
    expect(await mySkillsApi.restore(1)).toMatchObject({ id: 1 })
    expect(await (await mySkillsApi.downloadMarkdown(1)).blob.text()).toBe("# md")
    expect(await mySkillsApi.requestDraft({ intent: "test" })).toEqual({
      job_id: 11,
      status: "pending",
    })
    expect(await mySkillsApi.draftStatus(11)).toMatchObject({ status: "done" })
    expect(await mySkillsApi.confirmDraft(11, { skill_name: "Confirmed" })).toMatchObject({ id: 3 })
  })

  it("calls private tool endpoints", async () => {
    server.use(
      mock.get(`${BASE}/my/tools`, () => HttpResponse.json([{ id: 1, tool_name: "T1" }])),
      mock.get(`${BASE}/my/tools/1`, () => HttpResponse.json({ id: 1, tool_name: "T1" })),
      mock.post(`${BASE}/my/tools`, async ({ request }) =>
        HttpResponse.json({ tool: await request.json(), warnings: [] }),
      ),
      mock.put(`${BASE}/my/tools/1`, async ({ request }) =>
        HttpResponse.json({ tool: { id: 1, ...(await request.json() as object) }, warnings: [] }),
      ),
      mock.post(`${BASE}/my/tools/1/archive`, () => HttpResponse.json({ id: 1 })),
      mock.post(`${BASE}/my/tools/1/restore`, () => HttpResponse.json({ id: 1 })),
    )

    expect(await myToolsApi.list()).toHaveLength(1)
    expect(await myToolsApi.get(1)).toMatchObject({ id: 1 })
    expect(
      await myToolsApi.create({ tool_name: "T", description: "d", url: "https://x.io" }),
    ).toMatchObject({ warnings: [] })
    expect(await myToolsApi.update(1, { description: "u" })).toMatchObject({
      tool: { id: 1, description: "u" },
    })
    expect(await myToolsApi.archive(1)).toMatchObject({ id: 1 })
    expect(await myToolsApi.restore(1)).toMatchObject({ id: 1 })
  })
})

describe("configBundlesApi, deviceApi, notificationsApi, and knowledgeApi", () => {
  it("calls configBundlesApi endpoints", async () => {
    server.use(
      mock.get(`${BASE}/config-bundles`, () => HttpResponse.json([{ id: 1, name: "B1" }])),
      mock.get(`${BASE}/config-bundles/1`, () => HttpResponse.json({ id: 1, name: "B1" })),
      mock.get(`${BASE}/config-bundles/1/effective`, () =>
        HttpResponse.json({ bundle_id: 1, version_hash: "h" }),
      ),
      mock.post(`${BASE}/config-bundles`, async ({ request }) =>
        HttpResponse.json({ id: 2, ...(await request.json() as object) }),
      ),
      mock.post(`${BASE}/config-bundles/from-agent`, async ({ request }) =>
        HttpResponse.json({ id: 3, ...(await request.json() as object) }),
      ),
      mock.patch(`${BASE}/config-bundles/1`, async ({ request }) =>
        HttpResponse.json({ id: 1, ...(await request.json() as object) }),
      ),
      mock.delete(`${BASE}/config-bundles/1`, () => new HttpResponse(null, { status: 204 })),
      mock.post(`${BASE}/config-bundles/1/clone`, async ({ request }) =>
        HttpResponse.json({ id: 4, ...(await request.json() as object) }),
      ),
      mock.post(`${BASE}/config-bundles/1/items`, () => HttpResponse.json({ id: 1 })),
      mock.post(`${BASE}/config-bundles/1/items/remove`, () => HttpResponse.json({ id: 1 })),
      mock.get(`${BASE}/config-bundles/1/export`, () => new HttpResponse("zip")),
    )

    expect(await configBundlesApi.list()).toHaveLength(1)
    expect(await configBundlesApi.get(1)).toMatchObject({ id: 1 })
    expect(await configBundlesApi.effective(1)).toMatchObject({ version_hash: "h" })
    expect(
      await configBundlesApi.create({
        agent_id: 1,
        name: "B2",
        description: "d",
        skill_ids: [],
        tool_ids: [],
      }),
    ).toMatchObject({ id: 2 })
    expect(
      await configBundlesApi.createFromAgent({ agent_id: 1, name: "B3", description: "d" }),
    ).toMatchObject({ id: 3 })
    expect(await configBundlesApi.update(1, { name: "Updated" })).toMatchObject({ name: "Updated" })
    await expect(configBundlesApi.remove(1)).resolves.toBeUndefined()
    expect(await configBundlesApi.clone(1, { name: "Copy" })).toMatchObject({ id: 4, name: "Copy" })
    expect(await configBundlesApi.addItems(1, { skill_ids: [1] })).toMatchObject({ id: 1 })
    expect(await configBundlesApi.removeItems(1, { skill_ids: [1] })).toMatchObject({ id: 1 })
    expect(await (await configBundlesApi.exportZip(1)).blob.text()).toBe("zip")
  })

  it("calls deviceApi, notificationsApi, and knowledgeApi endpoints", async () => {
    server.use(
      mock.post(`${BASE}/device/tokens`, () =>
        HttpResponse.json({ id: 1, name: "pc", access_token: "dev-tok", token_type: "bearer" }),
      ),
      mock.get(`${BASE}/device`, () => HttpResponse.json([{ id: 1, name: "pc" }])),
      mock.post(`${BASE}/device/1/revoke`, () => HttpResponse.json({ id: 1, name: "pc" })),
      mock.get(`${BASE}/notifications`, () => HttpResponse.json([{ id: 1 }])),
      mock.get(`${BASE}/notifications/unread-count`, () => HttpResponse.json({ unread: 4 })),
      mock.post(`${BASE}/notifications/read-all`, () => HttpResponse.json({ updated: 4 })),
      mock.post(`${BASE}/notifications/1/read`, () => new HttpResponse(null, { status: 204 })),
      mock.post(`${BASE}/knowledge/ingest/file`, () =>
        HttpResponse.json({ succeeded: [1], skipped_duplicates: [], failed: [] }),
      ),
      mock.post(`${BASE}/knowledge/ingest/web`, () =>
        HttpResponse.json({ job_id: 5, status: "pending" }),
      ),
      mock.get(`${BASE}/knowledge/ingest/jobs/5`, () =>
        HttpResponse.json({ id: 5, status: "done" }),
      ),
      mock.post(`${BASE}/knowledge/search`, () =>
        HttpResponse.json([{ id: "c1", score: 0.9, payload: {} }]),
      ),
      mock.post(`${BASE}/knowledge/search/agentic`, () =>
        HttpResponse.json({
          initial_subqueries: [],
          reasoning: "ok",
          evidence: [],
          iterations: [],
          degraded_to_hybrid: false,
        }),
      ),
    )

    expect(await deviceApi.issueToken({ scope: "runtime:full", name: "pc" })).toMatchObject({
      access_token: "dev-tok",
    })
    expect(await deviceApi.list({ active_only: true })).toHaveLength(1)
    expect(await deviceApi.revoke(1)).toMatchObject({ id: 1 })

    expect(await notificationsApi.list({ unread_only: true })).toHaveLength(1)
    expect(await notificationsApi.unreadCount()).toEqual({ unread: 4 })
    expect(await notificationsApi.markAllRead()).toEqual({ updated: 4 })
    await expect(notificationsApi.markRead(1)).resolves.toBeUndefined()

    expect(
      await knowledgeApi.ingestFile({
        source: "doc.pdf",
        document_type: "manual",
        knowledge_type: "reference",
        knowledge_pack_id: 1,
      }),
    ).toMatchObject({ succeeded: [1] })
    expect(
      await knowledgeApi.ingestWeb({
        query: "docker",
        document_type: "manual",
        knowledge_type: "reference",
        knowledge_pack_id: 1,
      }),
    ).toMatchObject({ job_id: 5 })
    expect(await knowledgeApi.job(5)).toMatchObject({ status: "done" })
    expect(await knowledgeApi.search({ query: "q", config_bundle_id: 1 })).toHaveLength(1)
    expect(await knowledgeApi.searchAgentic({ query: "q", config_bundle_id: 1 })).toMatchObject({
      reasoning: "ok",
    })
  })
})
