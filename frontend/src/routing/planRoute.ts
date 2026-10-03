import { ApiRequestError, fetchRoutes } from '../api/client'
import type { RouteResult } from '../api/types'
import { buildRouteRequest } from './useRouteDraft'
import type { RouteDraft } from './useRouteDraft'

/** Names the point an error refers to (`from`, `via[1]`, `to`) the way the panel calls it. */
function pointName(field: unknown): string {
  if (field === 'from') return 'Punkt A'
  if (field === 'to') return 'Punkt B'
  const stop = typeof field === 'string' ? /^via\[(\d+)\]$/.exec(field) : null
  return stop ? `Przystanek ${Number(stop[1]) + 1}` : 'Jeden z punktów'
}

/** Turns a POST /route failure into a message for the user; the contract's error codes are in docs/ROUTING_GRAPH.md. */
export function describeRouteError(err: unknown): string {
  if (!(err instanceof ApiRequestError)) return err instanceof Error ? err.message : 'Nie udało się wyznaczyć trasy.'
  const field = err.details?.field
  if (err.status === 404 && field) return `${pointName(field)} jest za daleko od drogi dla wybranego środka transportu. Wskaż punkt bliżej drogi.`
  if (err.status === 404) return 'Nie znaleziono trasy między tymi punktami.'
  if (err.status === 422 && err.code === 'OUT_OF_AREA') return `${pointName(field)} leży poza Krakowem.`
  if (err.status === 429) return 'Za dużo zapytań o trasę. Poczekaj chwilę i spróbuj ponownie.'
  if (err.status === 502) return 'Silnik tras jest chwilowo niedostępny. Spróbuj za moment.'
  return err.message
}

/**
 * Asks the backend (POST /route) for routes for the chosen points, stops, profile and requirements.
 * Car and bike: with requirements rank 1 is the best route for them and rank 2 the fastest (when different);
 * without, a single fastest route. Pedestrians get one route when stops are given.
 */
export async function planRoute(draft: RouteDraft, signal?: AbortSignal): Promise<RouteResult[]> {
  const request = buildRouteRequest(draft)
  if (!request) throw new ApiRequestError(0, 'INCOMPLETE', 'Ustaw punkt początkowy i cel.')
  const routes = await fetchRoutes(request, signal)
  if (routes.length === 0) throw new ApiRequestError(404, 'NOT_FOUND', 'Nie znaleziono trasy między tymi punktami.')
  return routes
}
