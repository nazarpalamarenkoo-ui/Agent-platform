import { QueryClient } from "@tanstack/react-query"
import { isApiError } from "@/lib/http"

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) =>
        !(isApiError(error) && error.status >= 400 && error.status < 500) &&
        failureCount < 2,
    },
  },
})