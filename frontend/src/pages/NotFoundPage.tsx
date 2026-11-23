import { Link } from "react-router"
import { textLink } from "@/lib/forms"

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-md px-6 py-24">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">404</p>
      <h1 className="mt-3 font-serif text-4xl">Page not found</h1>
      <p className="mt-4 text-muted-foreground">
        This address doesn't exist or has been moved.{" "}
        <Link to="/" className={textLink}>
          Go to home
        </Link>
      </p>
    </div>
  )
}