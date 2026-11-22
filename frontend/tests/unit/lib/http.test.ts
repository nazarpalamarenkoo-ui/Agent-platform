import { http as mock, HttpResponse } from "msw"
import { ApiError, http } from "../../../src/lib/http"
import { getToken, setToken } from "../../../src/auth/session"
import { server } from "../../server"

const BASE = "http://localhost:8000"

describe("http client", () => {
  it("adds the Bearer token and JSON body", async () => {
    setToken("abc")
    let seen: Record<string, unknown> = {}
    server.use(
      mock.post(`${BASE}/echo`, async ({ request }) => {
        seen = {
          auth: request.headers.get("authorization"),
          type: request.headers.get("content-type"),
          body: await request.json(),
        }
        return HttpResponse.json({ ok: true })
      }),
    )

    const result = await http.post<{ ok: boolean }>("/echo", { a: 1 })

    expect(result).toEqual({ ok: true })
    expect(seen).toEqual({
      auth: "Bearer abc",
      type: "application/json",
      body: { a: 1 },
    })
  })

  it("does not add Authorization when auth: false", async () => {
    setToken("abc")
    let header: string | null = "unset"
    server.use(
      mock.get(`${BASE}/public`, ({ request }) => {
        header = request.headers.get("authorization")
        return HttpResponse.json({})
      }),
    )

    await http.get("/public", { auth: false })

    expect(header).toBeNull()
  })

  it("serializes the query and skips undefined and null", async () => {
    let search = ""
    server.use(
      mock.get(`${BASE}/list`, ({ request }) => {
        search = new URL(request.url).search
        return HttpResponse.json([])
      }),
    )

    await http.get("/list", {
      query: { limit: 10, offset: 0, include_archived: true, domain_id: undefined, agent_id: null },
    })

    expect(search).toBe("?limit=10&offset=0&include_archived=true")
  })

  it("returns undefined for 204", async () => {
    server.use(mock.delete(`${BASE}/x/1`, () => new HttpResponse(null, { status: 204 })))

    await expect(http.delete("/x/1")).resolves.toBeUndefined()
  })

  it("clears the session on 401", async () => {
    setToken("expired")
    server.use(
      mock.get(`${BASE}/users/me`, () =>
        HttpResponse.json({ detail: "Could not validate credentials" }, { status: 401 }),
      ),
    )

    await expect(http.get("/users/me")).rejects.toMatchObject({ status: 401 })
    expect(getToken()).toBeNull()
  })

  it("does not clear the session on 401 for a public request", async () => {
    setToken("keep")
    server.use(
      mock.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ detail: "nope" }, { status: 401 }),
      ),
    )

    await expect(http.post("/auth/login", {}, { auth: false })).rejects.toBeInstanceOf(ApiError)
    expect(getToken()).toBe("keep")
  })

  it("takes the message from a string detail", async () => {
    server.use(
      mock.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ detail: "Incorrect email or password" }, { status: 400 }),
      ),
    )

    const error = await http.post("/auth/login", {}, { auth: false }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 400, message: "Incorrect email or password" })
  })

  it("splits 422 errors by field", async () => {
    server.use(
      mock.post(`${BASE}/auth/signup`, () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" },
              { loc: ["body", "password"], msg: "Field required", type: "missing" },
            ],
          },
          { status: 422 },
        ),
      ),
    )

    const error = (await http.post("/auth/signup", {}, { auth: false }).catch((e: unknown) => e)) as ApiError

    expect(error.status).toBe(422)
    expect(error.fieldErrors).toEqual({
      email: "value is not a valid email address",
      password: "Field required",
    })
  })

  it("reads Retry-After on 429", async () => {
    server.use(
      mock.post(`${BASE}/catalog/hint`, () =>
        HttpResponse.json({ detail: "Too many requests" }, { status: 429, headers: { "Retry-After": "30" } }),
      ),
    )

    const error = (await http.post("/catalog/hint", {}).catch((e: unknown) => e)) as ApiError

    expect(error.status).toBe(429)
    expect(error.retryAfter).toBe(30)
  })

  it("turns a network error into an ApiError with status 0", async () => {
    server.use(mock.get(`${BASE}/down`, () => HttpResponse.error()))

    await expect(http.get("/down")).rejects.toMatchObject({ name: "ApiError", status: 0 })
  })
})