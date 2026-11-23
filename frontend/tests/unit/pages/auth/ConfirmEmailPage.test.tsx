import { screen } from "@testing-library/react"
import { http as mock, HttpResponse } from "msw"
import { getToken } from "../../../../src/auth/session"
import { server } from "../../../server"
import { renderApp } from "../../../render"

const BASE = "http://localhost:8000"

const alice = {
  id: 1,
  username: "alice",
  email: "alice@example.com",
  role: "user",
  tokens_used: 0,
  token_limit: 100,
}

describe("email confirmation", () => {
  it("sends the token once (even in StrictMode) and logs in", async () => {
    const tokens: (string | null)[] = []
    server.use(
      mock.post(`${BASE}/auth/signup-confirmation`, ({ request }) => {
        tokens.push(new URL(request.url).searchParams.get("token"))
        return HttpResponse.json({ access_token: "tok", token_type: "bearer" })
      }),
      mock.get(`${BASE}/users/me`, () => HttpResponse.json(alice)),
    )

    renderApp("/confirm-email/abc123")

    expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument()
    expect(tokens).toEqual(["abc123"])
    expect(getToken()).toBe("tok")
  })

  it("reports that the email is already confirmed", async () => {
    server.use(
      mock.post(`${BASE}/auth/signup-confirmation`, () =>
        HttpResponse.json({ detail: "Email has been already confirmed" }),
      ),
    )

    renderApp("/confirm-email/abc123")

    expect(await screen.findByText("Email already confirmed. You can log in.")).toBeInTheDocument()
    expect(getToken()).toBeNull()
  })

  it("shows an error for an expired link", async () => {
    server.use(
      mock.post(`${BASE}/auth/signup-confirmation`, () =>
        HttpResponse.json({ detail: "Invalid or expired token" }, { status: 400 }),
      ),
    )

    renderApp("/confirm-email/bad")

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or expired token")
  })
})