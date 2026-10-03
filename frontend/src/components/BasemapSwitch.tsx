import type { Basemap } from './MapView'

const OPTIONS: { id: Basemap; label: string }[] = [
  { id: 'map', label: 'Mapa' },
  { id: 'satellite', label: 'Satelita' },
]

/** "Mapa / Satelita" switch in the bottom-left corner, like the layers button in Google Maps. */
export default function BasemapSwitch({ basemap, onChange }: { basemap: Basemap; onChange: (b: Basemap) => void }) {
  return (
    <div
      className="pointer-events-auto absolute bottom-6 left-3 flex rounded-full bg-white p-1 shadow-lg ring-1 ring-black/5"
      role="radiogroup"
      aria-label="Rodzaj mapy"
    >
      {OPTIONS.map((o) => (
        <button
          key={o.id}
          role="radio"
          aria-checked={basemap === o.id}
          onClick={() => onChange(o.id)}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
            basemap === o.id ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-100'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
