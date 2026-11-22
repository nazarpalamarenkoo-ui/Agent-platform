import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import { MemoryRouter, Route, Routes } from "react-router"
import { RequireAuth } from "../../../src/auth/RequireAuth"
import { getToken, setToken } from "../../../src/auth/session"
import { server } from "../../server"
import type { UserRead, UserRole } from "../../../src/types/Index"

const BASE = "http://localhost:8000"

const userWith = (role: UserRole): UserRead => ({
  id: 1,
  username: "u",
  email: "u@example.com",
  role,
  tokens_used: 0,
  token_limit: 100,
})

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<p>login page</p>} />
          <Route path="/" element={<p>home page</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/app" element={<p>app page</p>} />
          </Route>
          <Route element={<RequireAuth role="admin" />}>
            <Route path="/admin" element={<p>admin page</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function meReturns(user: UserRead) {
  server.use(mock.get(`${BASE}/users/me`, () => HttpResponse.json(user)))
}

describe("RequireAuth", () => {
  it("redirects to /login without a token", async () => {
    renderAt("/app")

    expect(await screen.findByText("login page")).toBeInTheDocument()
  })

  it("lets a logged-in user through", async () => {
    setToken("tok")
    meReturns(userWith("user"))

    renderAt("/app")

    expect(await screen.findByText("app page")).toBeInTheDocument()
  })

  it("keeps a regular user out of the admin area", async () => {
    setToken("tok")
    meReturns(userWith("user"))

    renderAt("/admin")

    expect(await screen.findByText("home page")).toBeInTheDocument()
  })

  it("lets an admin into the admin area", async () => {
    setToken("tok")
    meReturns(userWith("admin"))

    renderAt("/admin")

    expect(await screen.findByText("admin page")).toBeInTheDocument()
  })

  it("an expired token redirects to /login and clears the session", async () => {
    setToken("expired")
    server.use(
      mock.get(`${BASE}/users/me`, () =>
        HttpResponse.json({ detail: "Could not validate credentials" }, { status: 401 }),
      ),
    )

    renderAt("/app")

    expect(await screen.findByText("login page")).toBeInTheDocument()
    expect(getToken()).toBeNull()
  })
})