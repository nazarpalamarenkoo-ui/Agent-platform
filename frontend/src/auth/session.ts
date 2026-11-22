const STORAGE_KEY = "auth.access_token"

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStored(value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, value)
  } catch {
  }
}

let token: string | null = readStored()
const listeners = new Set<() => void>()

function emit(): void {
  listeners.forEach((listener) => listener())
}

export const getToken = (): string | null => token

export function setToken(next: string): void {
  token = next
  writeStored(next)
  emit()
}

export function clearSession(): void {
  if (token === null) return
  token = null
  writeStored(null)
  emit()
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key !== null && event.key !== STORAGE_KEY) return
    token = readStored()
    emit()
  })
}