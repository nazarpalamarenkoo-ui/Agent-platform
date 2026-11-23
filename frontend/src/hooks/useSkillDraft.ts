import { useCallback, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { mySkillsApi } from "@/api"
import { catalogKeys } from "@/hooks/useCatalog"
import { isApiError } from "@/lib/http"
import {
  clearStoredJob,
  draftErrorMessage,
  pollDelay as defaultPollDelay,
  readStoredJob,
  storeJob,
} from "@/lib/skillDraft"
import type {
  MySkillRead,
  SkillDraftConfirm,
  SkillDraftRequest,
  SkillDraftResult,
  SkillDraftStatus,
} from "@/types/Index"

export type DraftPhase =
  | { name: "idle" }
  | { name: "requesting" }
  | { name: "waiting"; jobId: number; label: "Queued" | "Generating" }
  | { name: "ready"; jobId: number; draft: SkillDraftResult }
  | { name: "failed"; message: string }
  | { name: "error"; message: string }
  | { name: "saved"; skill: MySkillRead | null }

interface UseSkillDraftOptions {
  configBundleId?: number | null
  onSaved?: (skill: MySkillRead) => void
  pollDelay?: (updateCount: number) => number
}

export interface RequestDraftArgs {
  intent: string
  sourceText?: string
  knowledgePackIds?: number[]
  autoPacks?: boolean
}

export function useSkillDraft({
  configBundleId = null,
  onSaved,
  pollDelay = defaultPollDelay,
}: UseSkillDraftOptions = {}) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<number | null>(readStoredJob)
  const [saved, setSaved] = useState<{ skill: MySkillRead | null } | null>(null)

  const refreshSkills = () => {
    void queryClient.invalidateQueries({ queryKey: catalogKeys.skills })
  }

  const request = useMutation({
    mutationFn: ({ intent, sourceText, knowledgePackIds, autoPacks }: RequestDraftArgs) => {
      const body: SkillDraftRequest = { intent }
      if (configBundleId !== null) body.config_bundle_id = configBundleId
      if (sourceText?.trim()) body.source_text = sourceText.trim()
      if (knowledgePackIds && knowledgePackIds.length > 0) {
        body.knowledge_pack_ids = knowledgePackIds
      }
      if (autoPacks) body.auto_packs = true
      return mySkillsApi.requestDraft(body)
    },
    onSuccess: (job) => {
      storeJob(job.job_id)
      setJobId(job.job_id)
    },
  })

  const status = useQuery({
    queryKey: ["skill-draft", jobId],
    enabled: jobId !== null && saved === null,
    staleTime: 0,
    queryFn: async ({ signal }): Promise<SkillDraftStatus | null> => {
      if (jobId === null) return null
      try {
        return await mySkillsApi.draftStatus(jobId, { signal })
      } catch (error) {
        if (isApiError(error) && (error.status === 404 || error.status === 403)) {
          clearStoredJob()
          return null
        }
        throw error
      }
    },
    refetchInterval: (query) => {
      if (query.state.status === "error") return false
      const data = query.state.data
      if (data === null) return false
      if (data && (data.status === "done" || data.status === "failed")) return false
      return pollDelay(query.state.dataUpdateCount)
    },
  })

  const confirm = useMutation({
    mutationFn: ({ id, body }: { id: number; body: SkillDraftConfirm }) =>
      mySkillsApi.confirmDraft(id, body),
    onSuccess: (skill) => {
      clearStoredJob()
      setSaved({ skill })
      refreshSkills()
      onSaved?.(skill)
    },
    onError: (error) => {
      if (isApiError(error) && error.status === 409) {
        clearStoredJob()
        setSaved({ skill: null })
        refreshSkills()
      }
    },
  })

  const { reset: resetRequest } = request
  const { reset: resetConfirm } = confirm

  const discard = useCallback(() => {
    clearStoredJob()
    setJobId(null)
    setSaved(null)
    resetRequest()
    resetConfirm()
  }, [resetRequest, resetConfirm])

  const requestDraft = useCallback(
    (args: RequestDraftArgs) => {
      discard()
      request.mutate(args)
    },
    [discard, request],
  )

  const save = useCallback(
    (body: SkillDraftConfirm) => {
      if (jobId !== null) confirm.mutate({ id: jobId, body })
    },
    [jobId, confirm],
  )

  const phase = ((): DraftPhase => {
    if (saved) return { name: "saved", skill: saved.skill }
    if (jobId === null) return request.isPending ? { name: "requesting" } : { name: "idle" }
    if (status.isError) return { name: "error", message: draftErrorMessage(status.error) }

    const data = status.data
    if (data === undefined) return { name: "waiting", jobId, label: "Queued" }
    if (data === null) return { name: "idle" }
    if (data.status === "failed") {
      return { name: "failed", message: data.error ?? "Draft generation failed." }
    }
    if (data.status === "done") {
      return data.draft
        ? { name: "ready", jobId, draft: data.draft }
        : { name: "failed", message: "The draft came back empty." }
    }
    return { name: "waiting", jobId, label: data.status === "running" ? "Generating" : "Queued" }
  })()

  const confirmConflict = isApiError(confirm.error) && confirm.error.status === 409

  return {
    phase,
    requestDraft,
    requestError: request.isError ? draftErrorMessage(request.error) : null,
    save,
    isSaving: confirm.isPending,
    saveError: confirm.isError && !confirmConflict ? draftErrorMessage(confirm.error) : null,
    discard,
    retryStatus: () => {
      void status.refetch()
    },
    busy: phase.name === "requesting" || phase.name === "waiting" || phase.name === "ready",
  }
}

export type SkillDraftApi = ReturnType<typeof useSkillDraft>
