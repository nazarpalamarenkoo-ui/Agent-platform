import { Outlet } from "react-router"
import { APP_NAME } from "@/lib/brand"

export function AuthLayout() {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <aside className="hidden flex-col justify-between bg-ink p-12 text-beige-100 lg:flex">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-beige-300">
          {APP_NAME}
        </p>

        <div>
          <h2 className="font-serif text-5xl leading-[1.05]">
            Agents, skills and knowledge in one place.
          </h2>
          <p className="mt-6 max-w-sm text-beige-300">
            Build your own agent configurations, connect knowledge bases and
            run them in a local runtime.
          </p>
        </div>

        <div className="flex items-center gap-3 font-mono text-xs text-beige-300">
          <span className="h-2 w-2 bg-red-bright" aria-hidden="true" />
          <span>v0.1</span>
        </div>
      </aside>

      <main className="flex items-center px-6 py-16 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <Outlet />
        </div>
      </main>
    </div>
  )
}