import { useRef, useState } from 'react'
import type { RouteResult } from '../api/types'
import { describeRouteError, planRoute } from './planRoute'
import { buildRouteRequest } from './useRouteDraft'
import type { RouteDraft } from './useRouteDraft'

type PlanState = {
  /** The request the state belongs to; results of an older request are ignored once the choices change. */
  key: string
  status: 'loading' | 'done' | 'error'
  routes: RouteResult[]
  error: string | null
  selected: number
}

/** Runs {@link planRoute} for the current draft and keeps its result, loading flag and selected alternative. */
export function useRoutePlan(draft: RouteDraft) {
  const key = JSON.stringify(buildRouteRequest(draft))
  const [state, setState] = useState<PlanState | null>(null)
  const ctrl = useRef<AbortController | null>(null)

  // Results only count while they match the current points, profile and requirements.
  const current = state && state.key === key ? state : null

  const run = async () => {
    ctrl.current?.abort()
    const c = new AbortController()
    ctrl.current = c
    setState({ key, status: 'loading', routes: [], error: null, selected: 0 })
    try {
      const routes = await planRoute(draft, c.signal)
      if (!c.signal.aborted) setState({ key, status: 'done', routes, error: null, selected: 0 })
    } catch (err) {
      if (c.signal.aborted) return
      setState({ key, status: 'error', routes: [], error: describeRouteError(err), selected: 0 })
    }
  }

  return {
    status: current?.status ?? 'idle',
    routes: current?.routes ?? [],
    error: current?.error ?? null,
    selected: current?.selected ?? 0,
    run,
    /** Shows routes computed elsewhere (the assistant) as the result for `draft`; they count while the draft stays as given. */
    adopt: (draft: RouteDraft, routes: RouteResult[]) =>
      setState({ key: JSON.stringify(buildRouteRequest(draft)), status: 'done', routes, error: null, selected: 0 }),
    select: (index: number) => setState((s) => (s ? { ...s, selected: index } : s)),
    /** Forget the result and cancel a running request (e.g. when leaving route mode). */
    clear: () => {
      ctrl.current?.abort()
      setState(null)
    },
  }
}

export type RoutePlanApi = ReturnType<typeof useRoutePlan>
