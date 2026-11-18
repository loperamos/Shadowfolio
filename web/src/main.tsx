import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/charts/styles.css";

import { MantineProvider } from "@mantine/core";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";

import { App } from "./App";
import { AuthBoundary, isSignInReturn } from "./auth/AuthBoundary";
import { LandingPage } from "./landing/LandingPage";
import { theme } from "./ui/theme";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider theme={theme}>
      <BrowserRouter>
        <Routes>
          {/* The landing page is public; everything else needs a signed-in user. */}
          <Route path="/" element={<Home />} />
          <Route
            path="*"
            element={
              <AuthBoundary>
                <App />
              </AuthBoundary>
            }
          />
        </Routes>
      </BrowserRouter>
    </MantineProvider>
  </StrictMode>,
);

/** The site's root: the landing page, or the sign-in provider sending the user back there, which the app finishes. */
function Home() {
  return isSignInReturn(window.location.search) ? (
    <AuthBoundary>
      <App />
    </AuthBoundary>
  ) : (
    <LandingPage />
  );
}
