import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http as mock, HttpResponse } from "msw"
import { server } from "../../../server"
import { renderApp } from "../../../render"

const BASE = "http://localhost:8000"

async function fill() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText("Username"), "alice")
  await user.type(screen.getByLabelText("Email"), "alice@example.com")
  await user.type(screen.getByLabelText("Password"), "Passw0rdAA")
  await user.click(screen.getByRole("button", { name: "Create account" }))
}

describe("signup page", () => {
  it("asks the user to check their email after success", async () => {
    let body: unknown
    server.use(
      mock.post(`${BASE}/auth/signup`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ detail: "Email has been sent" })
      }),
    )
    renderApp("/signup")

    await fill()

    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument()
    expect(screen.getByText("alice@example.com")).toBeInTheDocument()
    expect(body).toEqual({ username: "alice", email: "alice@example.com", password: "Passw0rdAA" })
  })

  it("shows validation errors next to the fields", async () => {
    server.use(
      mock.post(`${BASE}/auth/signup`, () =>
        HttpResponse.json(
          { detail: [{ loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" }] },
          { status: 422 },
        ),
      ),
    )
    renderApp("/signup")

    await fill()

    expect(await screen.findByText("value is not a valid email address")).toBeInTheDocument()
  })

  it("shows a backend business error as a general message", async () => {
    server.use(
      mock.post(`${BASE}/auth/signup`, () =>
        HttpResponse.json({ detail: "Username 'alice' already exists" }, { status: 400 }),
      ),
    )
    renderApp("/signup")

    await fill()

    expect(await screen.findByRole("alert")).toHaveTextContent("Username 'alice' already exists")
  })
})