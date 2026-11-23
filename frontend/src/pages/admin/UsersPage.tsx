import { useState } from "react"
import { DataPage } from "@/components/DataPage"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { useAdminUsers, useResetUsage, useSetTokenLimit } from "@/hooks/useAdminUsers"
import { getErrorMessage } from "@/lib/http"
import type { AdminUserRead } from "@/types/Index"
import { Link } from "react-router"
import { textLink } from "@/lib/forms"

interface UserRowProps {
  user: AdminUserRead
  busy: boolean
  onSave: (id: number, tokenLimit: number) => void
  onReset: (id: number) => void
}

function UserRow({ user, busy, onSave, onReset }: UserRowProps) {
  const [value, setValue] = useState(String(user.token_limit))
  const parsed = Number(value)
  const valid = value.trim() !== "" && Number.isInteger(parsed) && parsed >= 0
  const changed = valid && parsed !== user.token_limit

  return (
    <tr className="border-t border-hairline/15 align-middle">
      <td className="py-3 pr-4 font-medium">
        <Link to={`/admin/users/${user.id}`} className={textLink}>
          {user.username}
        </Link>
      </td>
      <td className="py-3 pr-4 text-muted-foreground">{user.email}</td>
      <td className="py-3 pr-4 font-mono text-xs">{user.role}</td>
      <td className="py-3 pr-4 font-mono text-xs tabular-nums">
        {user.tokens_used.toLocaleString("en-US")}
      </td>
      <td className="py-3 pr-4">
        <input
          type="number"
          min={0}
          aria-label={`Token limit for ${user.username}`}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className="h-8 w-28 rounded-md border border-hairline/30 bg-transparent px-2 font-mono text-xs tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </td>
      <td className="py-3">
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={busy || !changed}
            onClick={() => onSave(user.id, parsed)}
          >
            Save
          </Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => onReset(user.id)}>
            Reset usage
          </Button>
        </div>
      </td>
    </tr>
  )
}

export function UsersPage() {
  const query = useAdminUsers()
  const setLimit = useSetTokenLimit()
  const reset = useResetUsage()
  const busy = setLimit.isPending || reset.isPending
  const error = setLimit.error ?? reset.error

  return (
    <DataPage
      kicker="Admin"
      title="Users"
      description="Manage token limits and usage."
      query={query}
      empty="No users."
    >
      {(users) => (
        <>
          {error ? (
            <div className="mb-6">
              <Notice tone="error">{getErrorMessage(error)}</Notice>
            </div>
          ) : null}

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="font-mono text-xs uppercase tracking-[0.15em] text-muted-foreground">
                  <th className="pb-3 pr-4 font-normal">User</th>
                  <th className="pb-3 pr-4 font-normal">Email</th>
                  <th className="pb-3 pr-4 font-normal">Role</th>
                  <th className="pb-3 pr-4 font-normal">Used</th>
                  <th className="pb-3 pr-4 font-normal">Limit</th>
                  <th className="pb-3 font-normal" />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <UserRow
                    key={`${user.id}:${user.token_limit}`}
                    user={user}
                    busy={busy}
                    onSave={(id, tokenLimit) => setLimit.mutate({ id, tokenLimit })}
                    onReset={(id) => reset.mutate(id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </DataPage>
  )
}