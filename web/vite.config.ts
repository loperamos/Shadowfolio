import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The repo's .env, shared with the backend.
const REPO_ROOT = "..";
const ENV_PREFIX = "SHADOWFOLIO_";
const HOST_ENV = "SHADOWFOLIO_HOST";
const PORT_ENV = "SHADOWFOLIO_PORT";
// Listening on every interface; to reach the backend from this machine, use the loopback address.
const ALL_INTERFACES = "0.0.0.0";
const LOOPBACK = "127.0.0.1";
// The backend serves its whole API under this prefix (API_PREFIX in the backend's web app).
const API_PREFIX = "/api";

export default defineConfig(({ command, mode }) => {
  if (command !== "serve") {
    return { plugins: [react()] };
  }

  // Only read here, never exposed to the browser code (Vite exposes VITE_-prefixed variables only).
  const env = loadEnv(mode, REPO_ROOT, ENV_PREFIX);
  const host = env[HOST_ENV];
  const port = env[PORT_ENV];
  if (!host || !port) {
    throw new Error(`${HOST_ENV} and ${PORT_ENV} must be set in the repo's .env`);
  }
  const backendUrl = `http://${host === ALL_INTERFACES ? LOOPBACK : host}:${port}`;

  return {
    plugins: [react()],
    server: {
      // Same address as the backend: set SHADOWFOLIO_HOST=0.0.0.0 to open both to your network.
      host,
      // Local development only: the dev server forwards API calls to the backend, so the browser
      // sees a single origin and the backend needs no CORS setup. How the deployed frontend
      // reaches the backend is still open (see SPEC.md, open questions).
      proxy: { [API_PREFIX]: backendUrl },
    },
  };
});
