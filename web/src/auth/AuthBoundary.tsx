import { Auth0Provider, type AppState, useAuth0 } from "@auth0/auth0-react";
import { Alert, Button, Center, Loader, Stack, Text, Title } from "@mantine/core";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { apiErrorMessage } from "../api/errors";
import { client } from "../api/generated/client.gen";
import { type SignInSettings, signInSettings } from "../api/generated";
import { AuthContext, type Auth } from "./useAuth";

type SettingsState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; settings: SignInSettings | null };

/**
 * Renders the app only for a signed-in user: it gets the sign-in settings from the backend, signs the user in with the
 * provider (Auth0) when they are not, and puts their token on every API call. The rest of the app knows the user only
 * through useAuth, so the provider can be swapped here.
 */
export function AuthBoundary({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SettingsState>({ status: "loading" });
  const navigate = useNavigate();

  useEffect(() => {
    signInSettings()
      .then(({ data, error, response }) =>
        setState(response?.ok ? { status: "loaded", settings: data ?? null } : { status: "error", message: apiErrorMessage(error) }),
      )
      .catch(() => setState({ status: "error", message: "Could not reach the backend." }));
  }, []);

  if (state.status === "loading") {
    return <Waiting />;
  }
  if (state.status === "error") {
    return <Notice title="Cannot sign in">{state.message}</Notice>;
  }
  const { settings } = state;
  if (settings === null) {
    return (
      <Notice title="Sign-in is not set up">
        Set AUTH0_DOMAIN, AUTH0_CLIENT_ID and AUTH0_AUDIENCE in the repository&apos;s .env (see .env.example), then restart
        the backend.
      </Notice>
    );
  }
  return (
    <Auth0Provider
      domain={settings.domain}
      clientId={settings.client_id}
      authorizationParams={{ audience: settings.audience, redirect_uri: window.location.origin }}
      // Stays signed in across reloads: refresh tokens when the API allows offline access, else the provider's session.
      cacheLocation="localstorage"
      useRefreshTokens
      useRefreshTokensFallback
      // Back to the page that asked to sign in.
      onRedirectCallback={(appState?: AppState) => navigate(appState?.returnTo ?? "/", { replace: true })}
    >
      <SignedIn>{children}</SignedIn>
    </Auth0Provider>
  );
}

function SignedIn({ children }: { children: ReactNode }) {
  const { isLoading, isAuthenticated, error, user, loginWithRedirect, logout, getAccessTokenSilently } = useAuth0();
  // Whether API calls carry the user's token yet: the app renders only then, so none goes out unsigned.
  const [signing, setSigning] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    const interceptor = client.interceptors.request.use(async (request) => {
      request.headers.set("Authorization", `Bearer ${await getAccessTokenSilently()}`);
      return request;
    });
    setSigning(true);
    return () => {
      client.interceptors.request.eject(interceptor);
      setSigning(false);
    };
  }, [isAuthenticated, getAccessTokenSilently]);

  const auth = useMemo<Auth | null>(
    () =>
      user?.sub
        ? {
            user: { id: user.sub, name: user.name ?? user.email ?? user.sub, email: user.email ?? null },
            signOut: () => logout({ logoutParams: { returnTo: window.location.origin } }),
          }
        : null,
    [user, logout],
  );

  if (isLoading) {
    return <Waiting />;
  }
  if (!isAuthenticated || auth === null) {
    const returnTo = window.location.pathname + window.location.search;
    return <SignInScreen error={error?.message ?? null} onSignIn={() => loginWithRedirect({ appState: { returnTo } })} />;
  }
  return signing ? <AuthContext.Provider value={auth}>{children}</AuthContext.Provider> : <Waiting />;
}

function SignInScreen({ error, onSignIn }: { error: string | null; onSignIn: () => void }) {
  return (
    <Center mih="100vh">
      <Stack align="center" maw={420}>
        <Title order={1}>Shadowfolio</Title>
        <Text c="dimmed" ta="center">
          Simulated investment wallets with real market data. Sign in to see yours.
        </Text>
        {error && (
          <Alert color="red" w="100%">
            {error}
          </Alert>
        )}
        <Button size="md" onClick={onSignIn} data-autofocus>
          Sign in
        </Button>
      </Stack>
    </Center>
  );
}

function Waiting() {
  return (
    <Center mih="100vh">
      <Loader aria-label="Loading" />
    </Center>
  );
}

function Notice({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Center mih="100vh">
      <Alert color="yellow" title={title} maw={520}>
        {children}
      </Alert>
    </Center>
  );
}
