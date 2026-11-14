import { useCallback } from "react";
import { useNavigate } from "react-router";

/**
 * Changes the URL's query with `update`, replacing the history entry (so Back leaves the page instead of stepping
 * through views). `update` gets the query as it is now, not as it was when the caller last drew: a component that is
 * not drawn again on every change (e.g. a slow chart) still keeps the other parts of the query.
 */
export function useUpdateQuery(): (update: (current: URLSearchParams) => URLSearchParams) => void {
  const navigate = useNavigate();
  return useCallback(
    (update) => navigate({ search: update(new URLSearchParams(window.location.search)).toString() }, { replace: true }),
    [navigate],
  );
}
