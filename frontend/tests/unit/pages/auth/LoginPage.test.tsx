import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http as mock, HttpResponse } from "msw"
import { getToken, setToken } from "../../../../src/auth/session"
import { server } from "../../../server"
import { renderApp } from "../../../render"
import type { UserRead } from "../../../../src/types/Index"

const BASE = "http://localhost:8000"

const alice: UserRead = {
  id: 1,
  username: "alice",
  email: "alice@example.com",
  role: "user",
  tokens_used: 2500,
  token_limit: 10000,
}

async function fillAndSubmit(email: string, password: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText("Email"), email)
  await user.type(screen.getByLabelText("Password"), password)
  await user.click(screen.getByRole("button", { name: "Log in" }))
}

describe("login page", () => {
  it("redirects an anonymous visitor from home to login", async () => {
    renderApp("/")

    expect(await screen.findByRole("heading", { name: "Log in to your account" })).toBeInTheDocument()
  })

  it("shows a clear message for invalid credentials", async () => {
    server.use(
      mock.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ detail: "Incorrect email or password" }, { status: 400 }),
      ),
    )
    renderApp("/login")

    await fillAndSubmit("alice@example.com", "wrongpass")

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password")
    expect(getToken()).toBeNull()
  })

  it("successful login opens the profile", async () => {
    server.use(
      mock.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ access_token: "tok", token_type: "bearer" }),
      ),
      mock.get(`${BASE}/users/me`, () => HttpResponse.json(alice)),
    )
    renderApp("/login")

    await fillAndSubmit("alice@example.com", "Passw0rdAA")

    expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument()
    expect(screen.getByText(/alice@example\.com/)).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25")
    expect(getToken()).toBe("tok")
  })

  it("sends a logged-in user from /login back into the app", async () => {
    setToken("tok")
    server.use(mock.get(`${BASE}/users/me`, () => HttpResponse.json(alice)))

    renderApp("/login")

    expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument()
  })

  it("logging out returns to the login page", async () => {
    setToken("tok")
    server.use(mock.get(`${BASE}/users/me`, () => HttpResponse.json(alice)))
    renderApp("/")
    await screen.findByRole("heading", { name: "alice" })

    await userEvent.setup().click(screen.getByRole("button", { name: "Log out" }))

    expect(await screen.findByRole("heading", { name: "Log in to your account" })).toBeInTheDocument()
    expect(getToken()).toBeNull()
  })
})