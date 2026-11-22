import { http } from "@/lib/http"
import type {
  DetailResponse,
  ResetPasswordArgs,
  SignInArgs,
  SignUpArgs,
  SignupConfirmationResponse,
  Token,
} from "@/types/Index"

export const authApi = {
  login: (body: SignInArgs) =>
    http.post<Token>("/auth/login", body, { auth: false }),

  signup: (body: SignUpArgs) =>
    http.post<DetailResponse>("/auth/signup", body, { auth: false }),

  confirmSignup: (token: string) =>
    http.post<SignupConfirmationResponse>("/auth/signup-confirmation", undefined, {
      auth: false,
      query: { token },
    }),

  recoverPassword: (email: string) =>
    http.post<DetailResponse>("/auth/password-recovery", undefined, {
      auth: false,
      query: { email },
    }),

  resetPassword: (body: ResetPasswordArgs) =>
    http.patch<DetailResponse>("/auth/reset-password", body, { auth: false }),
}