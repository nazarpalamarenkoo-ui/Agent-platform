import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router"
import { QueryClientProvider } from "@tanstack/react-query"
import "@fontsource-variable/newsreader"
import "@fontsource-variable/hanken-grotesk"
import "@fontsource-variable/jetbrains-mono"
import App from "./App"
import { queryClient } from "@/lib/queryClient"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)