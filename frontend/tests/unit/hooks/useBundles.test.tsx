import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http as mock, HttpResponse } from "msw"
import {
  bundleKeys,
  useAddBundleItems,
  useBundle,
  useBundles,
  useCloneBundle,
  useCreateBundleFromAgent,
  useDeleteBundle,
  useEffectiveBundle,
  useRemoveBundleItems,
  useUpdateBundle,
} from "@/hooks/useBundles"
import type { ConfigBundleRead } from "@/types/Index"
import { server } from "../../server"

const BASE = "http://localhost:8000"

const sampleBundle: ConfigBundleRead = {
  id: 5,
  user_id: 1,
  agent_id: 2,
  name: "Starter",
  description: "Starter bundle",
  skills: [],
  tools: [],
  knowledge_packs: [],
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const removeQueries = vi.spyOn(client, "removeQueries")
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper, invalidate, removeQueries }
}

describe("useBundles hooks", () => {
  it("loads list, detail, and effective bundle", async () => {
    server.use(
      mock.get(`${BASE}/config-bundles`, () => HttpResponse.json([sampleBundle])),
      mock.get(`${BASE}/config-bundles/5`, () => HttpResponse.json(sampleBundle)),
      mock.get(`${BASE}/config-bundles/5/effective`, () =>
        HttpResponse.json({
          bundle_id: 5,
          agent_id: 2,
          agent_name: "Architect",
          skills: [],
          tools: [],
          packs: [],
          version_hash: "v1",
        }),
      ),
    )

    const { wrapper } = createWrapper()
    const list = renderHook(() => useBundles(), { wrapper })
    const detail = renderHook(() => useBundle(5), { wrapper })
    const effective = renderHook(() => useEffectiveBundle(5), { wrapper })

    await waitFor(() => expect(list.result.current.data).toEqual([sampleBundle]))
    await waitFor(() => expect(detail.result.current.data).toEqual(sampleBundle))
    await waitFor(() => expect(effective.result.current.data?.version_hash).toBe("v1"))
  })

  it("mutates bundles (createFromAgent, update, clone, addItems, removeItems, delete) and updates cache", async () => {
    server.use(
      mock.post(`${BASE}/config-bundles/from-agent`, () => HttpResponse.json(sampleBundle)),
      mock.patch(`${BASE}/config-bundles/5`, () =>
        HttpResponse.json({ ...sampleBundle, name: "Renamed" }),
      ),
      mock.post(`${BASE}/config-bundles/5/clone`, () =>
        HttpResponse.json({ ...sampleBundle, id: 6, name: "Cloned" }),
      ),
      mock.post(`${BASE}/config-bundles/5/items`, () => HttpResponse.json(sampleBundle)),
      mock.post(`${BASE}/config-bundles/5/items/remove`, () => HttpResponse.json(sampleBundle)),
      mock.delete(`${BASE}/config-bundles/5`, () => new HttpResponse(null, { status: 204 })),
    )

    const { client, wrapper, invalidate, removeQueries } = createWrapper()

    const fromAgent = renderHook(() => useCreateBundleFromAgent(), { wrapper })
    await act(async () => {
      await fromAgent.result.current.mutateAsync({ agent_id: 2, name: "Starter", description: "d" })
    })
    expect(client.getQueryData(bundleKeys.detail(5))).toEqual(sampleBundle)

    const update = renderHook(() => useUpdateBundle(5), { wrapper })
    await act(async () => {
      await update.result.current.mutateAsync({ name: "Renamed" })
    })
    expect(client.getQueryData(bundleKeys.detail(5))).toMatchObject({ name: "Renamed" })

    const clone = renderHook(() => useCloneBundle(5), { wrapper })
    await act(async () => {
      await clone.result.current.mutateAsync({ name: "Cloned" })
    })
    expect(client.getQueryData(bundleKeys.detail(6))).toMatchObject({ id: 6, name: "Cloned" })

    const addItems = renderHook(() => useAddBundleItems(5), { wrapper })
    await act(async () => {
      await addItems.result.current.mutateAsync({ skill_ids: [1] })
    })

    const removeItems = renderHook(() => useRemoveBundleItems(5), { wrapper })
    await act(async () => {
      await removeItems.result.current.mutateAsync({ skill_ids: [1] })
    })

    const del = renderHook(() => useDeleteBundle(), { wrapper })
    await act(async () => {
      await del.result.current.mutateAsync(5)
    })
    expect(removeQueries).toHaveBeenCalledWith({ queryKey: bundleKeys.detail(5) })
    expect(removeQueries).toHaveBeenCalledWith({ queryKey: bundleKeys.effective(5) })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: bundleKeys.list() })
  })
})
