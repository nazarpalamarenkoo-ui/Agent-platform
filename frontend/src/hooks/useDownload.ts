import { useMutation } from "@tanstack/react-query"
import { saveBlob } from "@/lib/download"
import { getErrorMessage, isApiError, type DownloadedFile } from "@/lib/http"

interface DownloadArgs {
  load: () => Promise<DownloadedFile>
  fallbackName: string
}

export function useDownload() {
  return useMutation({
    mutationFn: async ({ load, fallbackName }: DownloadArgs) => {
      const file = await load()
      saveBlob(file.blob, file.filename ?? fallbackName)
    },
  })
}

export function downloadErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 404) return "Nothing to download: it no longer exists."
    if (error.status === 0) return "Can't reach the server."
  }
  return getErrorMessage(error)
}
