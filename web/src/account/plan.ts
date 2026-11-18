import { useEffect, useState } from "react";

import { getMe, type UserResponse } from "../api/generated";

/**
 * The signed-in user, with their tier, what their plan allows and the keys they still need; null while loading or if it
 * could not load (the backend still refuses what the plan does not allow, with the reason). Change `refreshKey` to load
 * it again.
 */
export function useMe(refreshKey: unknown = null): UserResponse | null {
  const [me, setMe] = useState<UserResponse | null>(null);

  useEffect(() => {
    let current = true;
    getMe()
      .then(({ data }) => current && setMe(data ?? null))
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [refreshKey]);

  return me;
}

/** Why the user may not make another wallet, owning `owned`: null when they may, or while their plan is unknown. */
export function newWalletBlocked(me: UserResponse | null, owned: number | null): string | null {
  const allowed = me?.limits.wallets;
  if (allowed == null || owned === null || owned < allowed) {
    return null;
  }
  return `Your plan allows ${allowed} wallets; delete one to make another.`;
}

/** Why the user may not create another agent token, with `active` ones: null when they may, or while unknown. */
export function newTokenBlocked(me: UserResponse | null, active: number | null): string | null {
  const allowed = me?.limits.access_tokens;
  if (allowed == null || active === null || active < allowed) {
    return null;
  }
  return `Your plan allows ${allowed} agent tokens at once; revoke one to make another.`;
}
