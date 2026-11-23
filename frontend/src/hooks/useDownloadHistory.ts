import { useCallback, useMemo, useSyncExternalStore } from "react"
import { configBundlesApi } from "@/api"
import { useAuth } from "@/auth/useAuth"
import { useDownload } from "@/hooks/useDownload"
import type { ConfigBundleRead } from "@/types/Index"


export interface DownloadRecord {
  bundleId: number
  name: string
  filename: string
  at: string
}

const MAX_RECORDS = 8
const EVENT = "download-history:change"
const keyFor = (userId: number) => `downloadHistory.v1:${userId}`

function isRecord(value: unknown): value is DownloadRecord {
  if (typeof value !== "object" || value === null) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.bundleId === "number" &&
    typeof v.name === "string" &&
    typeof v.filename === "string" &&
    typeof v.at === "string"
  )
}

function readRaw(userId: number): string {
  try {
    return localStorage.getItem(keyFor(userId)) ?? ""
  } catch {
    return ""
  }
}

function parse(raw: string): DownloadRecord[] {
  if (!raw) return []
  try {
    const value: unknown = JSON.parse(raw)
    return Array.isArray(value) ? value.filter(isRecord) : []
  } catch {
    return []
  }
}

export function recordDownload(userId: number, record: DownloadRecord): void {
  const rest = parse(readRaw(userId)).filter((item) => item.bundleId !== record.bundleId)
  const next = [record, ...rest].slice(0, MAX_RECORDS)
  try {
    localStorage.setItem(keyFor(userId), JSON.stringify(next))
  } catch {
  }
  window.dispatchEvent(new Event(EVENT))
}

function subscribe(callback: () => void): () => void {
  window.addEventListener(EVENT, callback)
  window.addEventListener("storage", callback)
  return () => {
    window.removeEventListener(EVENT, callback)
    window.removeEventListener("storage", callback)
  }
}

export function useDownloadHistory(userId: number | undefined): DownloadRecord[] {
  const raw = useSyncExternalStore(
    subscribe,
    () => (userId === undefined ? "" : readRaw(userId)),
    () => "",
  )
  return useMemo(() => parse(raw), [raw])
}

export function useBundleZip() {
  const { user } = useAuth()
  const userId = user?.id
  const download = useDownload()
  const { mutate } = download

  const start = useCallback(
    (bundle: ConfigBundleRead) => {
      mutate({
        fallbackName: `bundle-${bundle.id}.zip`,
        load: async () => {
          const file = await configBundlesApi.exportZip(bundle.id)
          if (userId !== undefined) {
            recordDownload(userId, {
              bundleId: bundle.id,
              name: bundle.name,
              filename: file.filename ?? `bundle-${bundle.id}.zip`,
              at: new Date().toISOString(),
            })
          }
          return file
        },
      })
    },
    [mutate, userId],
  )

  return { start, isPending: download.isPending, isError: download.isError, error: download.error }
}