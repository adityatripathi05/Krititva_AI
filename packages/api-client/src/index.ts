/**
 * @krititva/api-client
 *
 * Placeholder — real types and client methods are emitted from the FastAPI
 * OpenAPI spec via codegen in M1.T3. This module exposes the shape only so
 * the web app compiles against a stable import surface.
 */

export const API_CLIENT_VERSION = "0.1.0-alpha.0" as const;

export type ApiClient = {
  readonly baseUrl: string;
};

export function createApiClient(baseUrl: string): ApiClient {
  return { baseUrl };
}
