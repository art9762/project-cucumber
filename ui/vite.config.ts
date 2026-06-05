import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The frontend talks to the analysis API through a single base URL configured
// via the `VITE_API_BASE` env var (see .env.example). Default points at the
// local analysis service on port 8113. We deliberately do NOT proxy `/api`
// here — the API client (src/api/client.ts) prefixes VITE_API_BASE directly,
// which keeps prod/dev behaviour identical and avoids hidden rewrite rules.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
  },
});
