import { useState, type FormEvent } from "react"
import { Link } from "react-router"
import { useMutation } from "@tanstack/react-query"
import { authApi } from "@/api"
import { FormField } from "@/components/FormField"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { fieldErrorsOf, formErrorOf, textLink } from "@/lib/forms"
import { AuthHeading } from "./AuthHeading"

const FIELDS = ["username", "email", "password"] as const

export function SignupPage() {
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const mutation = useMutation({ mutationFn: authApi.signup })

  const fieldErrors = fieldErrorsOf(mutation.error)
  const formError = formErrorOf(mutation.error, FIELDS)

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate({ username, email, password })
  }

  if (mutation.isSuccess) {
    return (
      <>
        <AuthHeading
          kicker="Sign up"
          title="Check your email"
          description={
            <>
              We've sent an email to <span className="text-foreground">{email}</span>. The
              confirmation link is valid for 14 hours.
            </>
          }
        />
        <p className="text-sm text-muted-foreground">
          Didn't get the email? Check your "Spam" folder or{" "}
          <button type="button" className={textLink} onClick={() => mutation.reset()}>
            sign up again
          </button>
          .
        </p>
      </>
    )
  }

  return (
    <>
      <AuthHeading kicker="Sign up" title="Create an account" />

      <form onSubmit={onSubmit} className="space-y-5">
        {formError ? <Notice tone="error">{formError}</Notice> : null}

        <FormField
          label="Username"
          autoComplete="username"
          required
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          error={fieldErrors.username}
        />
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
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
          hint="At least 8 characters: uppercase and lowercase letters and a digit."
        />

        <Button type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? "Creating…" : "Create account"}
        </Button>
      </form>

      <p className="mt-8 border-t border-hairline/15 pt-6 text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className={textLink}>
          Log in
        </Link>
      </p>
    </>
  )
}