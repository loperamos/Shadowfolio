import { createContext, useContext } from "react";

/** The signed-in user, as the rest of the app knows them: the sign-in provider stays inside this module. */
export type SignedInUser = {
  id: string; // as the provider gives it, e.g. "auth0|64f…": what owns the user's wallets
  name: string;
  email: string | null;
};

export type Auth = { user: SignedInUser; signOut: () => void };

export const AuthContext = createContext<Auth | null>(null);

/** The signed-in user and how to sign out; only under AuthBoundary, which renders the app only once signed in. */
export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (auth === null) {
    throw new Error("useAuth is only available inside AuthBoundary");
  }
  return auth;
}
