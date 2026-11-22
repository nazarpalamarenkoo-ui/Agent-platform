import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import { useAuth } from "../../../src/auth/useAuth"
import { getToken } from "../../../src/auth/session"
import { server } from "../../server"
import type { UserRead } from "../../../src/types/Index"

const BASE = "http://localhost:8000"

const alice: UserRead = {
  id: 1,
  username: "alice",
  email: "alice@example.com",
  role: "user",
  tokens_used: 0,
  token_limit: 100_000,
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe("useAuth", () => {
  it("login stores the token and loads the profile", async () => {
    server.use(
      mock.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ access_token: "tok", token_type: "bearer" }),
      ),
      mock.get(`${BASE}/users/me`, ({ request }) =>
        request.headers.get("authorization") === "Bearer tok"
          ? HttpResponse.json(alice)
          : HttpResponse.json({ detail: "no" }, { status: 401 }),
      ),
    )

    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.isAuthenticated).toBe(false)

    await act(async () => {
      await result.current.login({ email: alice.email, password: "Passw0rdAA" })
    })

    expect(getToken()).toBe("tok")
    await waitFor(() => expect(result.current.user?.username).toBe("alice"))
    expect(result.current.isAdmin).toBe(false)
  })

  it("logout clears the token and the profile", async () => {
    server.use(mock.get(`${BASE}/users/me`, () => HttpResponse.json(alice)))

    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() => result.current.loginWithToken("tok"))
    await waitFor(() => expect(result.current.user).toBeDefined())

    act(() => result.current.logout())

    expect(getToken()).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeUndefined()
  })
})