import { useState, type FormEvent, type ReactNode } from "react"
import { FormField } from "@/components/FormField"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/auth/useAuth"
import {
  useCreateAgent,
  useCreateCustomAgent,
  useCreateMySkill,
  useCreateMyTool,
  useCreateSkill,
  useCreateTool,
} from "@/hooks/useBundleBuilder"
import { fieldErrorsOf } from "@/lib/forms"
import { getErrorMessage } from "@/lib/http"
import type { ToolAuthType } from "@/types/Index"

const areaClass =
  "w-full rounded-md border border-hairline/30 bg-transparent p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

function Disclosure({
  label,
  children,
}: {
  label: string
  children: (close: () => void) => ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="text-right">
      <Button variant="outline" size="sm" onClick={() => setOpen((value) => !value)}>
        {open ? "Cancel" : label}
      </Button>
      {open ? (
        <div className="mt-3 rounded-lg border border-hairline/30 p-4 text-left">
          {children(() => setOpen(false))}
        </div>
      ) : null}
    </div>
  )
}


export function NewSkillForm({ onCreated }: { onCreated: (id: number) => void }) {
  return (
    <Disclosure label="+ New skill">
      {(close) => <SkillFields onCreated={onCreated} close={close} />}
    </Disclosure>
  )
}

function SkillFields({ onCreated, close }: { onCreated: (id: number) => void; close: () => void }) {
  const { isAdmin } = useAuth()
  const [skillName, setSkillName] = useState("")
  const [description, setDescription] = useState("")
  const [content, setContent] = useState("")
  const adminCreate = useCreateSkill()
  const myCreate = useCreateMySkill()
  const active = isAdmin ? adminCreate : myCreate
  const errors = fieldErrorsOf(active.error)

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = { skill_name: skillName.trim(), description: description.trim(), content }
    const options = {
      onSuccess: (skill: { id: number }) => {
        onCreated(skill.id)
        close()
      },
    }
    if (isAdmin) adminCreate.mutate(body, options)
    else myCreate.mutate(body, options)
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {!isAdmin ? (
        <p className="text-sm text-muted-foreground">
          The skill will be private: only you can see and use it.
        </p>
      ) : null}
      {active.isError && Object.keys(errors).length === 0 ? (
        <Notice tone="error">{getErrorMessage(active.error)}</Notice>
      ) : null}
      <FormField
        label="Skill name"
        required
        maxLength={100}
        value={skillName}
        onChange={(event) => setSkillName(event.target.value)}
        error={errors.skill_name}
      />
      <FormField
        label="Description"
        required
        maxLength={255}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        error={errors.description}
      />
      <div>
        <label className="mb-1.5 block text-sm" htmlFor="new-skill-content">
          Content
        </label>
        <textarea
          id="new-skill-content"
          required
          rows={6}
          maxLength={50_000}
          value={content}
          onChange={(event) => setContent(event.target.value)}
          className={areaClass}
        />
        {errors.content ? <p className="mt-1 text-xs text-red">{errors.content}</p> : null}
      </div>
      <Button type="submit" disabled={active.isPending}>
        {active.isPending ? "Creating…" : "Create skill"}
      </Button>
    </form>
  )
}

export function NewToolForm({ onCreated }: { onCreated: (id: number) => void }) {
  return (
    <Disclosure label="+ New tool">
      {(close) => <ToolFields onCreated={onCreated} close={close} />}
    </Disclosure>
  )
}

function ToolFields({ onCreated, close }: { onCreated: (id: number) => void; close: () => void }) {
  const { isAdmin } = useAuth()
  const [toolName, setToolName] = useState("")
  const [description, setDescription] = useState("")
  const [url, setUrl] = useState("")
  const [authType, setAuthType] = useState<ToolAuthType>("none")
  const [authDescription, setAuthDescription] = useState("")
  const [warnings, setWarnings] = useState<string[]>([])
  const adminCreate = useCreateTool()
  const myCreate = useCreateMyTool()
  const active = isAdmin ? adminCreate : myCreate
  const errors = fieldErrorsOf(active.error)

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = {
      tool_name: toolName.trim(),
      description: description.trim(),
      url: url.trim(),
      auth_type: authType,
      auth_description: authDescription.trim() || null,
    }
    if (isAdmin) {
      adminCreate.mutate(body, {
        onSuccess: (tool) => {
          onCreated(tool.id)
          close()
        },
      })
    } else {
      myCreate.mutate(body, {
        onSuccess: ({ tool, warnings: list }) => {
          onCreated(tool.id)
          if (list.length > 0) setWarnings(list)
          else close()
        },
      })
    }
  }

  if (warnings.length > 0) {
    return (
      <div className="space-y-3">
        <p className="text-sm">The tool was created, but the server has remarks:</p>
        {warnings.map((warning) => (
          <Notice key={warning}>{warning}</Notice>
        ))}
        <Button variant="outline" size="sm" onClick={close}>
          Done
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {!isAdmin ? (
        <p className="text-sm text-muted-foreground">
          The tool will be private: only you can see and use it.
        </p>
      ) : null}
      {active.isError && Object.keys(errors).length === 0 ? (
        <Notice tone="error">{getErrorMessage(active.error)}</Notice>
      ) : null}
      <FormField
        label="Tool name"
        required
        maxLength={100}
        value={toolName}
        onChange={(event) => setToolName(event.target.value)}
        error={errors.tool_name}
      />
      <FormField
        label="Description"
        required
        maxLength={255}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        error={errors.description}
      />
      <FormField
        label="URL"
        type="url"
        required
        maxLength={2048}
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        error={errors.url}
      />
      <div>
        <label className="mb-1.5 block text-sm" htmlFor="new-tool-auth">
          Authentication
        </label>
        <select
          id="new-tool-auth"
          value={authType}
          onChange={(event) => setAuthType(event.target.value as ToolAuthType)}
          className="h-10 w-full rounded-md border border-hairline/30 bg-transparent px-3 text-sm"
        >
          <option value="none">None</option>
          <option value="api_key">API key</option>
          <option value="bearer">Bearer token</option>
          <option value="oauth">OAuth</option>
        </select>
      </div>
      {authType !== "none" ? (
        <FormField
          label="Auth notes"
          maxLength={255}
          value={authDescription}
          onChange={(event) => setAuthDescription(event.target.value)}
          error={errors.auth_description}
        />
      ) : null}
      <Button type="submit" disabled={active.isPending}>
        {active.isPending ? "Creating…" : "Create tool"}
      </Button>
    </form>
  )
}


interface NewAgentFormProps {
  skillIds: number[]
  toolIds: number[]
  packIds: number[]
  onCreated: (agentId: number) => void
}

export function NewAgentForm(props: NewAgentFormProps) {
  return (
    <Disclosure label="+ New profile">
      {(close) => <AgentFields {...props} close={close} />}
    </Disclosure>
  )
}

function AgentFields({
  skillIds,
  toolIds,
  packIds,
  onCreated,
  close,
}: NewAgentFormProps & { close: () => void }) {
  const { isAdmin } = useAuth()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const adminCreate = useCreateAgent()
  const customCreate = useCreateCustomAgent()
  const active = isAdmin ? adminCreate : customCreate
  const errors = fieldErrorsOf(active.error)

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const base = {
      name: name.trim(),
      description: description.trim(),
      skill_ids: skillIds,
      tool_ids: toolIds,
    }
    if (isAdmin) {
      adminCreate.mutate(base, {
        onSuccess: (agent) => {
          onCreated(agent.id)
          close()
        },
      })
    } else {
      customCreate.mutate(
        { ...base, knowledge_pack_ids: packIds },
        {
          onSuccess: (bundle) => {
            onCreated(bundle.agent_id)
            close()
          },
        },
      )
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-sm text-muted-foreground">
        The profile is created with the {skillIds.length} skills and {toolIds.length} tools
        currently selected below
        {isAdmin ? "." : `, plus ${packIds.length} knowledge packs. A bundle with the same name is created for you as well.`}
      </p>
      {active.isError && Object.keys(errors).length === 0 ? (
        <Notice tone="error">{getErrorMessage(active.error)}</Notice>
      ) : null}
      <FormField
        label="Profile name"
        required
        maxLength={100}
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={errors.name}
      />
      <FormField
        label="Description"
        required={isAdmin}
        maxLength={255}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        error={errors.description}
      />
      <Button type="submit" disabled={active.isPending}>
        {active.isPending ? "Creating…" : "Create profile"}
      </Button>
    </form>
  )
}