import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http as mock, HttpResponse } from "msw"
import { server } from "../../../server"
import { renderApp } from "../../../render"

const BASE = "http://localhost:8000"

describe("password recovery", () => {
  it("sends the email in the query and shows a neutral message", async () => {
    let email: string | null = null
    server.use(
      mock.post(`${BASE}/auth/password-recovery`, ({ request }) => {
        email = new URL(request.url).searchParams.get("email")
        return HttpResponse.json({ detail: "Email has been sent" })
      }),
    )
    renderApp("/forgot-password")
    const user = userEvent.setup()

    await user.type(screen.getByLabelText("Email"), "alice@example.com")
    await user.click(screen.getByRole("button", { name: "Send link" }))

    expect(await screen.findByRole("status")).toHaveTextContent("If an account with this email exists")
    expect(email).toBe("alice@example.com")
  })

  it("does not send a request when the passwords do not match", async () => {
    renderApp("/reset-password/tok")
    const user = userEvent.setup()

    await user.type(screen.getByLabelText("New password"), "NewPassw0rd")
    await user.type(screen.getByLabelText("Repeat password"), "Different1")
    await user.click(screen.getByRole("button", { name: "Save password" }))

    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument()
  })

  it("resets the password using the token from the link", async () => {
    let body: unknown
    server.use(
      mock.patch(`${BASE}/auth/reset-password`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ detail: "Password updated successfully" })
      }),
    )
    renderApp("/reset-password/tok-from-email")
    const user = userEvent.setup()

    await user.type(screen.getByLabelText("New password"), "NewPassw0rd")
    await user.type(screen.getByLabelText("Repeat password"), "NewPassw0rd")
    await user.click(screen.getByRole("button", { name: "Save password" }))

    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument()
    expect(body).toEqual({ token: "tok-from-email", new_password: "NewPassw0rd" })
  })
})