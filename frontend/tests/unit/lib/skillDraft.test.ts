import { ApiError, filenameFromDisposition } from "@/lib/http"
import {
  clearStoredJob,
  draftErrorMessage,
  pollDelay,
  readStoredJob,
  storeJob,
} from "@/lib/skillDraft"

afterEach(() => sessionStorage.clear())

describe("pollDelay", () => {
  it("starts at 2s, grows gradually, and caps at 3s", () => {
    expect(pollDelay(0)).toBe(2000)
    expect(pollDelay(2)).toBe(2500)
    expect(pollDelay(4)).toBe(3000)
    expect(pollDelay(100)).toBe(3000)
  })
})

describe("draftErrorMessage", () => {
  it("includes retry wait time on 429 with retryAfter", () => {
    const error = new ApiError(429, "Too many", null, 30)
    expect(draftErrorMessage(error)).toBe("Too many requests. Try again in 30s.")
  })

  it("does not invent seconds on 429 without retryAfter", () => {
    expect(draftErrorMessage(new ApiError(429, "Too many"))).toBe(
      "Too many requests. Try again in a moment.",
    )
  })

  it("explains quota or duplicate name on 409", () => {
    expect(draftErrorMessage(new ApiError(409, "conflict"))).toMatch(/limit of 50.*already exists/)
  })

  it("reports unavailable queue on 503", () => {
    expect(draftErrorMessage(new ApiError(503, "Queue unavailable"))).toMatch(/queue is temporarily unavailable/)
  })

  it("handles network and generic errors", () => {
    expect(draftErrorMessage(new ApiError(0, "x"))).toBe("Can't reach the server.")
    expect(draftErrorMessage(new ApiError(400, "Bad intent"))).toBe("Bad intent")
    expect(draftErrorMessage(new Error("boom"))).toBe("boom")
  })
})

describe("stored job", () => {
  it("stores, reads, and clears job id", () => {
    expect(readStoredJob()).toBeNull()
    storeJob(42)
    expect(readStoredJob()).toBe(42)
    clearStoredJob()
    expect(readStoredJob()).toBeNull()
  })

  it("ignores invalid values in sessionStorage", () => {
    sessionStorage.setItem("skillDraft.jobId", "abc")
    expect(readStoredJob()).toBeNull()
    sessionStorage.setItem("skillDraft.jobId", "-3")
    expect(readStoredJob()).toBeNull()
  })
})

describe("filenameFromDisposition", () => {
  it("parses quoted and unquoted filename", () => {
    expect(filenameFromDisposition('attachment; filename="SKILL.md"')).toBe("SKILL.md")
    expect(filenameFromDisposition("attachment; filename=bundle.zip")).toBe("bundle.zip")
  })

  it("prefers UTF-8 filename*=", () => {
    expect(
      filenameFromDisposition(`attachment; filename="fallback.zip"; filename*=UTF-8''my%20bundle.zip`),
    ).toBe("my bundle.zip")
  })

  it("returns null when filename is absent", () => {
    expect(filenameFromDisposition(null)).toBeNull()
    expect(filenameFromDisposition("attachment")).toBeNull()
  })
})
