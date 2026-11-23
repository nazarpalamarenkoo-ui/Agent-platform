import { useState, type FormEvent } from "react"
import { Link, useParams } from "react-router"
import { useMutation } from "@tanstack/react-query"
import { authApi } from "@/api"
import { FormField } from "@/components/FormField"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { fieldErrorsOf, formErrorOf, textLink } from "@/lib/forms"
import { AuthHeading } from "./AuthHeading"

export function ResetPasswordPage() {
  const { token = "" } = useParams()
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [mismatch, setMismatch] = useState(false)
  const mutation = useMutation({
    mutationFn: (newPassword: string) =>
      authApi.resetPassword({ token, new_password: newPassword }),
  })

  const fieldErrors = fieldErrorsOf(mutation.error)
  const formError = formErrorOf(mutation.error, ["new_password"])

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (password !== confirm) {
      setMismatch(true)
      return
    }
    setMismatch(false)
    mutation.mutate(password)
  }

  if (mutation.isSuccess) {
    return (
      <>
        <AuthHeading kicker="Recovery" title="Password updated" />
        <p className="text-sm">
          You can now{" "}
          <Link to="/login" className={textLink}>
            log in with your new password
          </Link>
          .
        </p>
      </>
    )
  }

  return (
    <>
      <AuthHeading kicker="Recovery" title="New password" />

      <form onSubmit={onSubmit} className="space-y-5">
        {formError ? <Notice tone="error">{formError}</Notice> : null}

        <FormField
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.new_password}
          hint="At least 8 characters: uppercase and lowercase letters and a digit."
        />
        <FormField
          label="Repeat password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          error={mismatch ? "Passwords do not match" : undefined}
        />

        <Button type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save password"}
        </Button>
      </form>
    </>
  )
}