import { useState } from "react"
import { Link, useParams } from "react-router"
import { UserOverviewPanel } from "@/components/admin/UserOverviewPanel"
import { Notice } from "@/components/Notice"
import { PageContainer } from "@/components/PageContainer"
import { PageHeader } from "@/components/PageHeader"
import { Stamp } from "@/components/Stamp"
import { Button } from "@/components/ui/button"
import { useAdminUsers, useResetUsage, useSetTokenLimit } from "@/hooks/useAdminUsers"
import { textLink } from "@/lib/forms"
import { getErrorMessage } from "@/lib/http"
import type { AdminUserRead } from "@/types/Index"

function UsageControls({ user }: { user: AdminUserRead }) {
  const setLimit = useSetTokenLimit()
  const reset = useResetUsage()
  const [value, setValue] = useState(String(user.token_limit))

  const parsed = Number(value)
  const valid = value.trim() !== "" && Number.isInteger(parsed) && parsed >= 0
  const changed = valid && parsed !== user.token_limit
  const busy = setLimit.isPending || reset.isPending
  const error = setLimit.error ?? reset.error

  const percent =
    user.token_limit > 0
      ? Math.min(100, Math.round((user.tokens_used / user.token_limit) * 100))
      : 0

  return (
    <div className="mt-6 rounded-lg border border-hairline/30 p-4">
      <p className="font-mono text-sm tabular-nums">
        {user.tokens_used.toLocaleString("en-US")} / {user.token_limit.toLocaleString("en-US")} tokens
        <span className="text-muted-foreground"> · {percent}%</span>
      </p>
      <div
        role="progressbar"
        aria-label="Token usage"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="mt-2 h-1 bg-muted"
      >
        <div className="h-full bg-red" style={{ width: `${percent}%` }} />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          type="number"
          min={0}
          aria-label={`Token limit for ${user.username}`}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className="h-8 w-32 rounded-md border border-hairline/30 bg-transparent px-2 font-mono text-xs tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button
          size="sm"
          disabled={busy || !changed}
          onClick={() => setLimit.mutate({ id: user.id, tokenLimit: parsed })}
        >
          Save limit
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => reset.mutate(user.id)}
        >
          Reset usage
        </Button>
      </div>

      {error ? (
        <div className="mt-4">
          <Notice tone="error">{getErrorMessage(error)}</Notice>
        </div>
      ) : null}
    </div>
  )
}

export function UserProfilePage() {
  const { userId } = useParams()
  const id = Number(userId)
  const users = useAdminUsers()

  const back = (
    <Link to="/admin/users" className={textLink}>
      ← All users
    </Link>
  )

  if (!Number.isInteger(id) || id <= 0) {
    return (
      <PageContainer>
        <Notice tone="error">Invalid user id.</Notice>
        <p className="mt-4">{back}</p>
      </PageContainer>
    )
  }

  if (users.isPending) {
    return (
      <PageContainer>
        <p className="font-mono text-xs text-muted-foreground">Loading…</p>
      </PageContainer>
    )
  }

  if (users.isError) {
    return (
      <PageContainer>
        <Notice tone="error">{getErrorMessage(users.error)}</Notice>
        <p className="mt-4">{back}</p>
      </PageContainer>
    )
  }

  const user = users.data.find((u) => u.id === id)

  if (!user) {
    return (
      <PageContainer>
        <h1 className="font-serif text-4xl">User not found</h1>
        <p className="mt-4">{back}</p>
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader
        kicker="Admin · User profile"
        title={user.username}
        description={
          <span className="inline-flex flex-wrap items-center gap-2">
            {user.email} <Stamp>{user.role}</Stamp>
          </span>
        }
        actions={back}
      />

      <UsageControls key={`${user.id}:${user.token_limit}`} user={user} />

      <div className="mt-8">
        <UserOverviewPanel user={user} />
      </div>
    </PageContainer>
  )
}