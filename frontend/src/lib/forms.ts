import { getErrorMessage, isApiError } from "@/lib/http"

export function fieldErrorsOf(error: unknown): Record<string, string> {
  return isApiError(error) ? error.fieldErrors : {}
}

export function formErrorOf(error: unknown, fields: readonly string[]): string | null {
  if (!error) return null
  if (isApiError(error) && error.status === 422) {
    const shownNearFields = Object.keys(error.fieldErrors).some((key) => fields.includes(key))
    if (shownNearFields) return null
  }
  return getErrorMessage(error)
}
export const textLink =
  "underline underline-offset-4 decoration-hairline/40 transition-colors hover:text-red-deep hover:decoration-red"