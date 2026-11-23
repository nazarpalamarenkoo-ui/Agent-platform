import { DataPage } from "@/components/DataPage"
import { Button } from "@/components/ui/button"
import { useMarkAllRead, useMarkRead, useNotifications } from "@/hooks/useNotifications"
import { cn } from "@/lib/utils"
import type { NotificationType } from "@/types/Index"

const LABELS: Record<NotificationType, string> = {
  skill_archived: "Skill archived",
  tool_archived: "Tool archived",
}

export function NotificationsPage() {
  const query = useNotifications()
  const markRead = useMarkRead()
  const markAll = useMarkAllRead()

  return (
    <DataPage
      kicker="Inbox"
      title="Notifications"
      query={query}
      empty="No notifications."
      actions={
        <Button
          variant="outline"
          size="sm"
          disabled={markAll.isPending || !query.data?.some((n) => n.read_at === null)}
          onClick={() => markAll.mutate()}
        >
          Mark all as read
        </Button>
      }
    >
      {(items) => (
        <ul className="divide-y divide-hairline/15 border-y border-hairline/15">
          {items.map((item) => {
            const unread = item.read_at === null
            return (
              <li key={item.id} className="flex items-center gap-4 py-4">
                <span
                  aria-hidden
                  className={cn("size-2 shrink-0 rounded-full", unread ? "bg-red" : "bg-transparent")}
                />
                <div className="min-w-0 flex-1">
                  <p className={cn(unread && "font-medium")}>
                    {LABELS[item.type]}
                    {item.item_name ? `: ${item.item_name}` : ""}
                  </p>
                  <p className="font-mono text-xs text-muted-foreground">
                    {new Date(item.created_at).toLocaleString("en-US")}
                  </p>
                </div>
                {unread ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={markRead.isPending}
                    onClick={() => markRead.mutate(item.id)}
                  >
                    Mark as read
                  </Button>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </DataPage>
  )
}