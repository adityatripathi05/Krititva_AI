import "server-only";

import { serverApi } from "./server";

/**
 * First-run status for the /setup redirect. Fails closed to `true` (treat as
 * "already set up") if the backend is unreachable, so we never dead-end a user
 * on the setup screen when the API is simply down — they land on /login instead.
 */
export async function isBootstrapped(): Promise<boolean> {
  try {
    const { bootstrapped } = await serverApi<{ bootstrapped: boolean }>("/auth/bootstrap");
    return bootstrapped;
  } catch {
    return true;
  }
}
