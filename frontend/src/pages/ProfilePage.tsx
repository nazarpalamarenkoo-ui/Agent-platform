// src/pages/ProfilePage.tsx
import { useEffect, useRef, useState, type FormEvent } from "react"
import { Link } from "react-router"
import { Notice } from "@/components/Notice"
import { PageContainer } from "@/components/PageContainer"
import { PageHeader } from "@/components/PageHeader"
import { Stamp } from "@/components/Stamp"
import { Stat } from "@/components/Stat"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/auth/useAuth"
import { formatBundleAgents } from "@/hooks/useBundleBuilder"
import { useBundles } from "@/hooks/useBundles"
import { useAgents } from "@/hooks/useCatalog"
import {
  readLocalDeviceToken,
  useDevices,
  useIssueDeviceToken,
  useRevokeDevice,
} from "@/hooks/useDevices"
import { downloadErrorMessage } from "@/hooks/useDownload"
import { useBundleZip, useDownloadHistory } from "@/hooks/useDownloadHistory"
import { useMySkills, useMyTools } from "@/hooks/useMyLibrary"
import { textLink } from "@/lib/forms"
import { getErrorMessage } from "@/lib/http"
import type { ConfigBundleRead, DeviceRead, UserRole } from "@/types/Index"

const ROLE_LABELS: Record<UserRole, string> = {
  user: "User",
  admin: "Administrator",
  super_admin: "Super administrator",
}

const PREVIEW = 5

function Section({
  title,
  action,
  children,
}: {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="mt-12">
      <div className="mb-4 flex items-end justify-between gap-4">
        <h2 className="font-serif text-3xl">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>
}

function BundleZipButton({ bundle }: { bundle: ConfigBundleRead }) {
  const zip = useBundleZip()
  return (
    <div className="text-right">
      <Button variant="outline" size="sm" disabled={zip.isPending} onClick={() => zip.start(bundle)}>
        {zip.isPending ? "Preparing…" : "Download .zip"}
      </Button>
      {zip.isError ? (
        <p role="alert" className="mt-1 text-xs text-destructive">
          {downloadErrorMessage(zip.error)}
        </p>
      ) : null}
    </div>
  )
}

function maskToken(raw: string): string {
  if (raw.length <= 18) return "••••••••••••••••"
  return `${raw.slice(0, 10)}••••••••••••••••••••${raw.slice(-6)}`
}

interface DeviceAccessSectionProps {
  userId: number
  bundles: ConfigBundleRead[]
}

/**
 * Секція керування локальними токенами пристроїв (device_access_token).
 * Відображається ТІЛЬКИ самому користувачу в його особистому профілі (/profile).
 * Якщо активних пристроїв ще немає (перший вхід після реєстрації) — автоматично
 * випускає перший 30-денний токен пристрою.
 */
function DeviceAccessSection({ userId, bundles }: DeviceAccessSectionProps) {
  const devicesQuery = useDevices(true)
  const issue = useIssueDeviceToken(userId)
  const revoke = useRevokeDevice(userId)

  const [deviceName, setDeviceName] = useState("workstation")
  const [bundleId, setBundleId] = useState<string>("")
  const [freshToken, setFreshToken] = useState<string | null>(null)
  const [revealedIds, setRevealedIds] = useState<Set<number>>(new Set())
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  // Автоматично створюємо перший device_access_token після реєстрації, якщо список порожній
  const autoIssuedRef = useRef(false)
  useEffect(() => {
    if (autoIssuedRef.current) return
    if (devicesQuery.isSuccess && devicesQuery.data.length === 0 && !issue.isPending) {
      autoIssuedRef.current = true
      issue.mutate(
        { name: "default-pc", scope: "runtime:full", config_bundle_id: null },
        {
          onSuccess: (issued) => {
            setFreshToken(issued.access_token)
          },
        },
      )
    }
  }, [devicesQuery.isSuccess, devicesQuery.data, issue])

  function onGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanName = deviceName.trim() || "device"
    const parsedBundle = bundleId ? Number(bundleId) : null
    issue.mutate(
      {
        name: cleanName,
        scope: "runtime:full",
        config_bundle_id: parsedBundle,
      },
      {
        onSuccess: (issued) => {
          setFreshToken(issued.access_token)
        },
      },
    )
  }

  async function copyText(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedKey(key)
      setTimeout(() => setCopiedKey((prev) => (prev === key ? null : prev)), 2000)
    } catch {
      // ignore clipboard errors
    }
  }

  function toggleReveal(id: number) {
    setRevealedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const bundleName = (id: number | null) => {
    if (id === null) return "All bundles"
    return bundles.find((b) => b.id === id)?.name ?? `Bundle #${id}`
  }

  return (
    <Section title="Local Runtime access (Device token)">
      <div className="space-y-5 rounded-lg border border-hairline/30 p-5">
        <p className="text-sm text-muted-foreground">
          Use a 30-day <code className="font-mono text-xs">device_access_token</code> to connect your
          local <strong>Agent Runtime</strong> (<code className="font-mono text-xs">agentctl auth login</code>).
          This token is private to your account and is never visible to administrators.
        </p>

        {freshToken ? (
          <div className="space-y-3 rounded-md border border-red/40 bg-accent/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-xs uppercase tracking-wider text-red-deep">
                Active Device Access Token (valid for 30 days)
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void copyText("fresh-raw", freshToken)}
                >
                  {copiedKey === "fresh-raw" ? "Copied!" : "Copy token"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    void copyText("fresh-cmd", `agentctl auth login --token "${freshToken}"`)
                  }
                >
                  {copiedKey === "fresh-cmd" ? "Copied CLI command!" : "Copy CLI login command"}
                </Button>
              </div>
            </div>
            <pre className="overflow-x-auto rounded border border-hairline/20 bg-card p-3 font-mono text-xs select-all">
              {freshToken}
            </pre>
            <p className="font-mono text-xs text-muted-foreground">
              Run in terminal: <code>agentctl auth login --token "{maskToken(freshToken)}"</code>
            </p>
          </div>
        ) : null}

        <form onSubmit={onGenerate} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <div>
            <label htmlFor="device-name-input" className="mb-1.5 block text-xs">
              Device name
            </label>
            <input
              id="device-name-input"
              type="text"
              maxLength={100}
              required
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
              placeholder="e.g. home-pc, laptop"
              className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label htmlFor="device-bundle-select" className="mb-1.5 block text-xs">
              Bind to bundle (optional)
            </label>
            <select
              id="device-bundle-select"
              value={bundleId}
              onChange={(e) => setBundleId(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm"
            >
              <option value="">All my bundles</option>
              {bundles.map((b) => (
                <option key={b.id} value={String(b.id)}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>

          <Button type="submit" disabled={issue.isPending}>
            {issue.isPending ? "Generating…" : "Generate new token"}
          </Button>
        </form>

        {issue.isError ? <Notice tone="error">{getErrorMessage(issue.error)}</Notice> : null}
        {revoke.isError ? <Notice tone="error">{getErrorMessage(revoke.error)}</Notice> : null}

        {devicesQuery.isPending ? (
          <p className="font-mono text-xs text-muted-foreground">Loading devices…</p>
        ) : devicesQuery.isError ? (
          <Notice tone="error">{getErrorMessage(devicesQuery.error)}</Notice>
        ) : devicesQuery.data.length === 0 ? (
          <Muted>No active devices yet.</Muted>
        ) : (
          <ul className="divide-y divide-hairline/15 border-t border-hairline/15 pt-2">
            {devicesQuery.data.map((dev: DeviceRead) => {
              const storedRaw = readLocalDeviceToken(userId, dev.id)
              const revealed = revealedIds.has(dev.id)
              return (
                <li key={dev.id} className="space-y-2 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="flex items-center gap-2 font-medium">
                        <span>{dev.name}</span>
                        <Stamp>{bundleName(dev.config_bundle_id)}</Stamp>
                      </p>
                      <p className="font-mono text-xs text-muted-foreground">
                        Expires: {new Date(dev.expires_at).toLocaleDateString("en-US")}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {storedRaw ? (
                        <>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleReveal(dev.id)}
                          >
                            {revealed ? "Hide token" : "Show token"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => void copyText(`dev-${dev.id}`, storedRaw)}
                          >
                            {copiedKey === `dev-${dev.id}` ? "Copied!" : "Copy token"}
                          </Button>
                        </>
                      ) : null}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={revoke.isPending}
                        onClick={() => {
                          if (window.confirm(`Revoke device token "${dev.name}"?`)) {
                            revoke.mutate(dev.id)
                          }
                        }}
                      >
                        Revoke
                      </Button>
                    </div>
                  </div>

                  {storedRaw ? (
                    <p className="overflow-x-auto rounded border border-hairline/20 bg-card px-3 py-1.5 font-mono text-xs">
                      {revealed ? storedRaw : maskToken(storedRaw)}
                    </p>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </Section>
  )
}

export function ProfilePage() {
  const { user } = useAuth()
  const bundles = useBundles()
  const agents = useAgents()
  const mySkills = useMySkills()
  const myTools = useMyTools()
  const history = useDownloadHistory(user?.id)

  if (!user) return null

  const percent =
    user.token_limit > 0
      ? Math.min(100, Math.round((user.tokens_used / user.token_limit) * 100))
      : 0

  const recentBundles = [...(bundles.data ?? [])].sort((a, b) => b.id - a.id).slice(0, PREVIEW)

  const activeSkills = (mySkills.data ?? []).filter((s) => s.archived_at === null)
  const activeTools = (myTools.data ?? []).filter((t) => t.archived_at === null)

  return (
    <PageContainer>
      <PageHeader
        kicker="Profile"
        title={user.username}
        description={`${user.email} · ${ROLE_LABELS[user.role]}`}
        actions={
          <Link to="/config" className={textLink}>
            Open configurator
          </Link>
        }
      />

      <dl className="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Bundles" value={bundles.data?.length ?? "–"} />
        <Stat label="My skills" value={mySkills.data ? activeSkills.length : "–"} />
        <Stat label="My tools" value={myTools.data ? activeTools.length : "–"} />
        <Stat label="Tokens used" value={`${percent}%`} />
      </dl>

      <div className="mt-6 rounded-lg border border-hairline/30 p-4">
        <p className="font-mono text-sm tabular-nums">
          {user.tokens_used.toLocaleString("en-US")} / {user.token_limit.toLocaleString("en-US")} tokens
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
      </div>

      {/* Секція локального токена пристрою — видима виключно власнику профілю */}
      <DeviceAccessSection userId={user.id} bundles={bundles.data ?? []} />

      <Section
        title="Ready configs"
        action={
          (bundles.data?.length ?? 0) > PREVIEW ? (
            <Link to="/config" className={textLink}>
              All {bundles.data?.length} bundles
            </Link>
          ) : null
        }
      >
        {bundles.isPending ? (
          <p className="font-mono text-xs text-muted-foreground">Loading…</p>
        ) : bundles.isError ? (
          <Muted>{getErrorMessage(bundles.error)}</Muted>
        ) : recentBundles.length === 0 ? (
          <Muted>
            You have no bundles yet.{" "}
            <Link to="/config" className={textLink}>
              Build the first one
            </Link>
          </Muted>
        ) : (
          <ul className="divide-y divide-hairline/15 border-y border-hairline/15">
            {recentBundles.map((bundle) => (
              <li key={bundle.id} className="flex flex-wrap items-center justify-between gap-4 py-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{bundle.name}</p>
                  {bundle.description ? (
                    <p className="text-sm text-muted-foreground">{bundle.description}</p>
                  ) : null}
                  <p className="mt-1 font-mono text-xs text-muted-foreground">
                    {formatBundleAgents(bundle, agents.data)} · {bundle.skills.length} skills ·{" "}
                    {bundle.tools.length} tools · {bundle.knowledge_packs.length} packs
                  </p>
                </div>
                <BundleZipButton bundle={bundle} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Recent downloads">
        {history.length === 0 ? (
          <Muted>
            Nothing downloaded yet. Downloads are remembered in this browser only.
          </Muted>
        ) : (
          <ul className="divide-y divide-hairline/15 border-y border-hairline/15">
            {history.map((item) => (
              <li key={`${item.bundleId}:${item.at}`} className="flex items-center gap-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{item.name}</p>
                  <p className="truncate font-mono text-xs text-muted-foreground">{item.filename}</p>
                </div>
                <span className="shrink-0 font-mono text-xs text-muted-foreground">
                  {new Date(item.at).toLocaleString("en-US")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className="grid gap-10 md:grid-cols-2">
        <Section title="My skills">
          {mySkills.isPending ? (
            <p className="font-mono text-xs text-muted-foreground">Loading…</p>
          ) : activeSkills.length === 0 ? (
            <Muted>No private skills yet.</Muted>
          ) : (
            <ul className="divide-y divide-hairline/15 border-y border-hairline/15">
              {activeSkills.slice(0, PREVIEW).map((skill) => (
                <li key={skill.id} className="py-3">
                  <p className="flex items-center gap-2">
                    <span className="font-medium">{skill.skill_name}</span>
                    <Stamp>{skill.visibility.replace("_", " ")}</Stamp>
                  </p>
                  <p className="text-sm text-muted-foreground">{skill.description}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="My tools">
          {myTools.isPending ? (
            <p className="font-mono text-xs text-muted-foreground">Loading…</p>
          ) : activeTools.length === 0 ? (
            <Muted>No private tools yet.</Muted>
          ) : (
            <ul className="divide-y divide-hairline/15 border-y border-hairline/15">
              {activeTools.slice(0, PREVIEW).map((tool) => (
                <li key={tool.id} className="py-3">
                  <p className="flex items-center gap-2">
                    <span className="font-medium">{tool.tool_name}</span>
                    <Stamp>{tool.auth_type}</Stamp>
                  </p>
                  <p className="text-sm text-muted-foreground">{tool.description}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </PageContainer>
  )
}