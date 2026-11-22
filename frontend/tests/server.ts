import { http, HttpResponse } from "msw"
import { setupServer } from "msw/node"

const BASE = "http://localhost:8000"

export const server = setupServer(
  http.get(`${BASE}/notifications/unread-count`, () => HttpResponse.json({ unread: 0 })),
  http.get(`${BASE}/config-bundles`, () => HttpResponse.json([])),
  http.get(`${BASE}/agents`, () => HttpResponse.json([])),
  http.get(`${BASE}/my/skills`, () => HttpResponse.json([])),
  http.get(`${BASE}/my/tools`, () => HttpResponse.json([])),
  http.get(`${BASE}/device`, () =>
    HttpResponse.json([
      {
        id: 1,
        name: "default-pc",
        config_bundle_id: null,
        expires_at: "2026-12-31T00:00:00Z",
      },
    ]),
  ),
)