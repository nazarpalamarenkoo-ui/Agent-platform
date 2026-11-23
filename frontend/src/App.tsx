import { Route, Routes } from "react-router"
import { GuestOnly } from "@/auth/GuestOnly"
import { RequireAuth } from "@/auth/RequireAuth"
import { AppLayout } from "@/layouts/AppLayout"
import { AuthLayout } from "@/layouts/AuthLayout"
import { UsersPage } from "@/pages/admin/UsersPage"
import { ConfirmEmailPage } from "@/pages/auth/ConfirmEmailPage"
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage"
import { LoginPage } from "@/pages/auth/LoginPage"
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage"
import { SignupPage } from "@/pages/auth/SignupPage"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { NotificationsPage } from "@/pages/NotificationsPage"
import { ConfiguratorPage } from "@/pages/ConfiguratorPage" 
import { ProfilePage } from "@/pages/ProfilePage"
import { UserProfilePage } from "@/pages/admin/UserProfilePage"

const loading = (
  <p className="p-6 font-mono text-xs text-muted-foreground">Loading…</p>
)

export default function App() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route element={<GuestOnly />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        </Route>

        <Route path="/confirm-email/:token" element={<ConfirmEmailPage />} />
        <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
      </Route>
      
      <Route element={<RequireAuth fallback={loading} />}>
        <Route element={<AppLayout />}>
          <Route index element={<ProfilePage />} />
          <Route path="/config" element={<ConfiguratorPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />

          <Route element={<RequireAuth role="admin" fallback={loading} />}>
            <Route path="/admin/users" element={<UsersPage />} />
            <Route path="/admin/users/:userId" element={<UserProfilePage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}