// Generates the typed API client in src/api/generated from the backend's OpenAPI schema.
// Run `npm run generate` after changing the backend's routes or schemas; never edit the output by hand.
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "openapi.json",
  output: "src/api/generated",
  plugins: [
    // No base URL: requests go to the page's own origin, which the Vite dev server proxies to the backend.
    { name: "@hey-api/client-fetch", baseUrl: false },
    "@hey-api/typescript",
    "@hey-api/sdk",
  ],
});
