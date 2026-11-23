import { http as mock, HttpResponse } from "msw"
import { saveBlob } from "@/lib/download"
import { ApiError, http } from "@/lib/http"
import { setToken } from "@/auth/session"
import { server } from "../../server"

const BASE = "http://localhost:8000"

describe("http.download", () => {
  it("returns blob, filename from Content-Disposition, and sends auth token", async () => {
    setToken("tok")
    let auth: string | null = null
    server.use(
      mock.get(`${BASE}/config-bundles/5/export`, ({ request }) => {
        auth = request.headers.get("authorization")
        return new HttpResponse("zip-bytes", {
          headers: {
            "Content-Type": "application/zip",
            "Content-Disposition": 'attachment; filename="my-bundle.zip"',
          },
        })
      }),
    )

    const file = await http.download("/config-bundles/5/export")

    expect(file.filename).toBe("my-bundle.zip")
    expect(await new Response(file.blob).text()).toBe("zip-bytes")
    expect(auth).toBe("Bearer tok")
  })

  it("returns filename: null when Content-Disposition header is absent", async () => {
    server.use(mock.get(`${BASE}/f`, () => new HttpResponse("x")))

    expect((await http.download("/f")).filename).toBeNull()
  })

  it("converts 404 into an ApiError with the backend message", async () => {
    server.use(
      mock.get(`${BASE}/config-bundles/9/export`, () =>
        HttpResponse.json({ detail: "Config bundle not found" }, { status: 404 }),
      ),
    )

    const error = await http.download("/config-bundles/9/export").catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, message: "Config bundle not found" })
  })
})

describe("saveBlob", () => {
  const originalCreate = URL.createObjectURL
  const originalRevoke = URL.revokeObjectURL

  afterEach(() => {
    URL.createObjectURL = originalCreate
    URL.revokeObjectURL = originalRevoke
    vi.restoreAllMocks()
  })

  it("triggers download with the given filename and revokes the object URL", async () => {
    URL.createObjectURL = vi.fn(() => "blob:fake")
    URL.revokeObjectURL = vi.fn()
    const clicked: { href: string; download: string }[] = []
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push({ href: this.href, download: this.download })
    })

    saveBlob(new Blob(["x"]), "SKILL.md")

    expect(clicked).toEqual([{ href: "blob:fake", download: "SKILL.md" }])
    expect(document.querySelector("a[download]")).toBeNull()
    await vi.waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake"))
  })
})
