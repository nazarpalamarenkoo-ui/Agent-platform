import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { deviceApi } from "@/api"
import type { DeviceTokenCreate, DeviceTokenIssued } from "@/types/Index"

const ROOT = ["my-devices"] as const

export const deviceKeys = {
  all: ROOT,
  list: (activeOnly = true) => [...ROOT, { activeOnly }] as const,
}

const localTokenKey = (userId: number, deviceId: number) =>
  `device.localToken.v1:${userId}:${deviceId}`

export function saveLocalDeviceToken(userId: number, issued: DeviceTokenIssued): void {
  try {
    localStorage.setItem(localTokenKey(userId, issued.id), issued.access_token)
  } catch {
    // ignore storage quota errors
  }
}

export function readLocalDeviceToken(userId: number | undefined, deviceId: number): string | null {
  if (userId === undefined) return null
  try {
    return localStorage.getItem(localTokenKey(userId, deviceId))
  } catch {
    return null
  }
}

export function removeLocalDeviceToken(userId: number | undefined, deviceId: number): void {
  if (userId === undefined) return
  try {
    localStorage.removeItem(localTokenKey(userId, deviceId))
  } catch {
    // ignore
  }
}

export function useDevices(activeOnly = true) {
  return useQuery({
    queryKey: deviceKeys.list(activeOnly),
    queryFn: ({ signal }) => deviceApi.list({ active_only: activeOnly, limit: 100 }, { signal }),
  })
}

export function useIssueDeviceToken(userId: number | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: DeviceTokenCreate) => deviceApi.issueToken(body),
    onSuccess: (issued) => {
      if (userId !== undefined) {
        saveLocalDeviceToken(userId, issued)
      }
      void queryClient.invalidateQueries({ queryKey: deviceKeys.all })
    },
  })
}

export function useRevokeDevice(userId: number | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (deviceId: number) => deviceApi.revoke(deviceId),
    onSuccess: (_data, deviceId) => {
      removeLocalDeviceToken(userId, deviceId)
      void queryClient.invalidateQueries({ queryKey: deviceKeys.all })
    },
  })
}