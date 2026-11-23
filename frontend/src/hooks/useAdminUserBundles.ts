import { useQuery } from "@tanstack/react-query"
import { configBundlesApi } from "@/api"

export function useUserBundles(userId: number) {
  return useQuery({
    queryKey: ["admin", "users", userId, "bundles"] as const,
    queryFn: ({ signal }) => configBundlesApi.list({ user_id: userId, limit: 200 }, { signal }),
  })
}