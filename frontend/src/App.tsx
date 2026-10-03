import { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

type Health = {
  status: 'ok' | 'degraded' | 'down'
  version: string
  checks: Record<string, string>
}

/** Placeholder start screen: shows backend health until the map is built (branch frontend/map). */
export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => res.json())
      .then(setHealth)
      .catch((err: Error) => setError(err.message))
  }, [])

  return (
    <main className="mx-auto max-w-md p-6 font-sans">
      <h1 className="text-2xl font-bold">Rate Your Ride</h1>
      <p className="mt-1 text-gray-600">Szkielet — mapa pojawi się na gałęzi frontend/map.</p>

      <section className="mt-6 rounded-lg border border-gray-200 p-4">
        <h2 className="font-semibold">Stan usług</h2>
        {error && <p className="mt-2 text-red-600">Backend niedostępny: {error}</p>}
        {!health && !error && <p className="mt-2 text-gray-500">Sprawdzam…</p>}
        {health && (
          <ul className="mt-2 space-y-1">
            <li>backend: {health.status} (v{health.version})</li>
            {Object.entries(health.checks).map(([name, state]) => (
              <li key={name}>
                {name}: {state}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
