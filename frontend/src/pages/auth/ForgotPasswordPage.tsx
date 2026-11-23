import { useState, type FormEvent } from "react"
import { Link } from "react-router"
import { useMutation } from "@tanstack/react-query"
import { authApi } from "@/api"
import { FormField } from "@/components/FormField"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { fieldErrorsOf, formErrorOf, textLink } from "@/lib/forms"
import { AuthHeading } from "./AuthHeading"

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const mutation = useMutation({ mutationFn: authApi.recoverPassword })

  const fieldErrors = fieldErrorsOf(mutation.error)
  const formError = formErrorOf(mutation.error, ["email"])

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate(email)
  }

  return (
    <>
      <AuthHeading
        kicker="Recovery"
        title="Forgot your password?"
        description="Enter your account email and we'll send you a link to reset your password."
      />

      {mutation.isSuccess ? (
        <Notice>If an account with this email exists, we've sent it an email with a link.</Notice>
      ) : (
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

          <Button type="submit" className="w-full" disabled={mutation.isPending}>
            {mutation.isPending ? "Sending…" : "Send link"}
          </Button>
        </form>
      )}

      <p className="mt-8 border-t border-hairline/15 pt-6 text-sm text-muted-foreground">
        <Link to="/login" className={textLink}>
          Back to login
        </Link>
      </p>
    </>
  )
}