import { useEffect, useState } from "react";

import { getMe, type UserResponse } from "../api/generated";

/**
 * The signed-in user, with their tier and what their plan allows; null while loading or if it could not load (the
 * backend still refuses what the plan does not allow, with the reason).
 */
export function useMe(): UserResponse | null {
  const [me, setMe] = useState<UserResponse | null>(null);

  useEffect(() => {
    let current = true;
    getMe()
      .then(({ data }) => current && setMe(data ?? null))
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, []);

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
