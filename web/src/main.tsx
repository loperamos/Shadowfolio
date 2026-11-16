import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/charts/styles.css";

import { MantineProvider } from "@mantine/core";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { App } from "./App";
import { AuthBoundary } from "./auth/AuthBoundary";
import { theme } from "./ui/theme";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider theme={theme}>
      <BrowserRouter>
        <AuthBoundary>
          <App />
        </AuthBoundary>
      </BrowserRouter>
    </MantineProvider>
  </StrictMode>,
);
