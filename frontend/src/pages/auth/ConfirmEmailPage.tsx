import { useEffect, useRef } from "react"
import { Link, useNavigate, useParams } from "react-router"
import { useMutation } from "@tanstack/react-query"
import { authApi } from "@/api"
import { Notice } from "@/components/Notice"
import { useAuth } from "@/auth/useAuth"
import { getErrorMessage } from "@/lib/http"
import { textLink } from "@/lib/forms"
import { AuthHeading } from "./AuthHeading"

export function ConfirmEmailPage() {
  const { token = "" } = useParams()
  const { loginWithToken } = useAuth()
  const navigate = useNavigate()

  const mutation = useMutation({
    mutationFn: authApi.confirmSignup,
    onSuccess: (result) => {
      if ("access_token" in result) {
        loginWithToken(result.access_token)
        navigate("/", { replace: true })
      }
    },
  })

  const started = useRef(false)
  const { mutate } = mutation
  useEffect(() => {
    if (started.current) return
    started.current = true
    mutate(token)
  }, [mutate, token])

  return (
    <>
      <AuthHeading kicker="Sign up" title="Email confirmation" />

      {mutation.isError ? (
        <>
          <Notice tone="error">{getErrorMessage(mutation.error)}</Notice>
          <p className="mt-8 border-t border-hairline/15 pt-6 text-sm text-muted-foreground">
            The link may have expired.{" "}
            <Link to="/signup" className={textLink}>
              Sign up again
            </Link>
          </p>
        </>
      ) : mutation.isSuccess && "detail" in mutation.data ? (
        <>
          <Notice>Email already confirmed. You can log in.</Notice>
          <p className="mt-8 text-sm">
            <Link to="/login" className={textLink}>
              Go to login
            </Link>
          </p>
        </>
      ) : (
        <p className="font-mono text-xs text-muted-foreground">Confirming your address…</p>
      )}
    </>
  )
}