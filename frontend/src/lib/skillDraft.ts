import { getErrorMessage, isApiError } from "@/lib/http"

export function pollDelay(updateCount: number): number {
  return Math.min(3000, 2000 + updateCount * 250)
}

export function draftErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 429) {
      return `Too many requests.${error.retryAfter ? ` Try again in ${error.retryAfter}s.` : " Try again in a moment."}`
    }
    if (error.status === 409) {
      return "Can't create this skill: you've reached the limit of 50 custom skills, or a skill with this name already exists."
    }
    if (error.status === 503) {
      return "The generation queue is temporarily unavailable. Try again in a minute."
    }
    if (error.status === 0) {
      return "Can't reach the server."
    }
  }
  return getErrorMessage(error)
}

const STORAGE_KEY = "skillDraft.jobId"

export function readStoredJob(): number | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    const id = raw === null ? NaN : Number(raw)
    return Number.isInteger(id) && id > 0 ? id : null
  } catch {
    return null
  }
}

export function storeJob(id: number): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, String(id))
  } catch {
  }
}

export function clearStoredJob(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
  }
}
