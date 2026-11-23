import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { configBundlesApi } from "@/api"
import type {
  BundleItems,
  ConfigBundleClone,
  ConfigBundleFromAgent,
  ConfigBundleRead,
  ConfigBundleUpdate,
} from "@/types/Index"

const ROOT = ["bundles"] as const

export const bundleKeys = {
  all: ROOT,
  list: () => [...ROOT, "list"] as const,
  detail: (id: number) => [...ROOT, "detail", id] as const,
  effective: (id: number) => [...ROOT, "effective", id] as const,
}

export function useBundles() {
  return useQuery({
    queryKey: bundleKeys.list(),
    queryFn: ({ signal }) => configBundlesApi.list({ limit: 500 }, { signal }),
  })
}

export function useBundle(id: number) {
  return useQuery({
    queryKey: bundleKeys.detail(id),
    queryFn: ({ signal }) => configBundlesApi.get(id, { signal }),
  })
}

export function useEffectiveBundle(id: number) {
  return useQuery({
    queryKey: bundleKeys.effective(id),
    queryFn: ({ signal }) => configBundlesApi.effective(id, { signal }),
  })
}

function useApplyBundle() {
  const queryClient = useQueryClient()
  return (bundle: ConfigBundleRead) => {
    queryClient.setQueryData(bundleKeys.detail(bundle.id), bundle)
    void queryClient.invalidateQueries({ queryKey: bundleKeys.list() })
    void queryClient.invalidateQueries({ queryKey: bundleKeys.effective(bundle.id) })
  }
}

export function useCreateBundleFromAgent() {
  const apply = useApplyBundle()
  return useMutation({
    mutationFn: (body: ConfigBundleFromAgent) => configBundlesApi.createFromAgent(body),
    onSuccess: apply,
  })
}

export function useUpdateBundle(id: number) {
  const apply = useApplyBundle()
  return useMutation({
    mutationFn: (body: ConfigBundleUpdate) => configBundlesApi.update(id, body),
    onSuccess: apply,
  })
}

export function useCloneBundle(id: number) {
  const apply = useApplyBundle()
  return useMutation({
    mutationFn: (body: ConfigBundleClone) => configBundlesApi.clone(id, body),
    onSuccess: apply,
  })
}

export function useAddBundleItems(id: number) {
  const apply = useApplyBundle()
  return useMutation({
    mutationFn: (items: BundleItems) => configBundlesApi.addItems(id, items),
    onSuccess: apply,
  })
}

export function useRemoveBundleItems(id: number) {
  const apply = useApplyBundle()
  return useMutation({
    mutationFn: (items: BundleItems) => configBundlesApi.removeItems(id, items),
    onSuccess: apply,
  })
}

export function useDeleteBundle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => configBundlesApi.remove(id),
    onSuccess: (_result, id) => {
      queryClient.removeQueries({ queryKey: bundleKeys.detail(id) })
      queryClient.removeQueries({ queryKey: bundleKeys.effective(id) })
      void queryClient.invalidateQueries({ queryKey: bundleKeys.list() })
    },
  })
}