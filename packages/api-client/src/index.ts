/**
 * @krititva/api-client
 *
 * Placeholder — real types and client methods are to be emitted from the
 * FastAPI OpenAPI spec via codegen (still owed as of M1.T7; a dedicated
 * build-tooling task). Until then the web app uses hand-maintained types in
 * apps/web/lib/api/types.ts. This module exposes the shape only so the web app
 * compiles against a stable import surface.
 */

export const API_CLIENT_VERSION = "0.1.0-alpha.0" as const;

export type ApiClient = {
  readonly baseUrl: string;
};

export function createApiClient(baseUrl: string): ApiClient {
  return { baseUrl };
}
