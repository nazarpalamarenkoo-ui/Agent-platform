import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import {
  deviceKeys,
  readLocalDeviceToken,
  removeLocalDeviceToken,
  saveLocalDeviceToken,
  useDevices,
  useIssueDeviceToken,
  useRevokeDevice,
} from "@/hooks/useDevices"
import type { DeviceTokenIssued } from "@/types/Index"
import { server } from "../../server"

const BASE = "http://localhost:8000"

const issuedDevice: DeviceTokenIssued = {
  id: 12,
  name: "workstation",
  config_bundle_id: 5,
  expires_at: "2026-12-22T00:00:00Z",
  access_token: "device-secret-token",
  token_type: "bearer",
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { wrapper, invalidate }
}

describe("useDevices local token helpers and hooks", () => {
  it("saves, reads, and removes local device tokens per user and device", () => {
    expect(readLocalDeviceToken(undefined, 12)).toBeNull()
    expect(readLocalDeviceToken(1, 12)).toBeNull()

    saveLocalDeviceToken(1, issuedDevice)
    expect(readLocalDeviceToken(1, 12)).toBe("device-secret-token")
    expect(readLocalDeviceToken(2, 12)).toBeNull()

    removeLocalDeviceToken(undefined, 12)
    expect(readLocalDeviceToken(1, 12)).toBe("device-secret-token")

    removeLocalDeviceToken(1, 12)
    expect(readLocalDeviceToken(1, 12)).toBeNull()
  })

  it("loads devices, issues a device token (storing it locally), and revokes a device", async () => {
    server.use(
      mock.get(`${BASE}/device`, () =>
        HttpResponse.json([
          {
            id: 12,
            name: "workstation",
            config_bundle_id: 5,
            expires_at: "2026-12-22T00:00:00Z",
          },
        ]),
      ),
      mock.post(`${BASE}/device/tokens`, () => HttpResponse.json(issuedDevice, { status: 201 })),
      mock.post(`${BASE}/device/12/revoke`, () =>
        HttpResponse.json({
          id: 12,
          name: "workstation",
          config_bundle_id: 5,
          expires_at: "2026-12-22T00:00:00Z",
        }),
      ),
    )

    const { wrapper, invalidate } = createWrapper()

    const list = renderHook(() => useDevices(true), { wrapper })
    await waitFor(() => expect(list.result.current.data).toHaveLength(1))

    const issue = renderHook(() => useIssueDeviceToken(42), { wrapper })
    await act(async () => {
      await issue.result.current.mutateAsync({
        scope: "runtime:full",
        name: "workstation",
        config_bundle_id: 5,
      })
    })
    expect(readLocalDeviceToken(42, 12)).toBe("device-secret-token")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: deviceKeys.all })

    const revoke = renderHook(() => useRevokeDevice(42), { wrapper })
    await act(async () => {
      await revoke.result.current.mutateAsync(12)
    })
    expect(readLocalDeviceToken(42, 12)).toBeNull()
    expect(invalidate).toHaveBeenCalledTimes(2)
  })
})
