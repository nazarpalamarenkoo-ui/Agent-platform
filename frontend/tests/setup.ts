import "@testing-library/jest-dom/vitest"
import { clearSession } from "../src/auth/session"
import { server } from "./server"

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))

afterEach(() => {
  server.resetHandlers()
  clearSession()
  localStorage.clear()
})

afterAll(() => server.close())