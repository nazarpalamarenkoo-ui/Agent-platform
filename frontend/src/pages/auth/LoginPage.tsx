import { useState, type FormEvent } from "react"
import { Link } from "react-router"
import { useMutation } from "@tanstack/react-query"
import { FormField } from "@/components/FormField"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/auth/useAuth"
import { fieldErrorsOf, formErrorOf, textLink } from "@/lib/forms"
import { isApiError } from "@/lib/http"
import { AuthHeading } from "./AuthHeading"

const FIELDS = ["email", "password"] as const

export function LoginPage() {
  const { login } = useAuth()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const mutation = useMutation({ mutationFn: login })

  const fieldErrors = fieldErrorsOf(mutation.error)
  const formError =
    isApiError(mutation.error) && mutation.error.status === 400
      ? "Invalid email or password"
      : formErrorOf(mutation.error, FIELDS)

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate({ email, password })
  }

  return (
    <>
      <AuthHeading kicker="Login" title="Log in to your account" />

      <form onSubmit={onSubmit} className="space-y-5">
        {formError ? <Notice tone="error">{formError}</Notice> : null}

        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors.email}
        />
        <FormField
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
        />

        <Button type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? "Logging in…" : "Log in"}
        </Button>
      </form>

      <div className="mt-8 space-y-2 border-t border-hairline/15 pt-6 text-sm text-muted-foreground">
        <p>
          <Link to="/forgot-password" className={textLink}>
            Forgot your password?
          </Link>
        </p>
        <p>
          Don't have an account?{" "}
          <Link to="/signup" className={textLink}>
            Create one
          </Link>
        </p>
      </div>
    </>
  )
}