import type { Basemap } from './MapView'

const ICON_PROPS = { width: 24, height: 24, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinejoin: 'round', strokeLinecap: 'round' } as const

const OPTIONS: { id: Basemap; label: string; icon: React.ReactNode }[] = [
  {
    id: 'map',
    label: 'Mapa',
    icon: (
      <svg {...ICON_PROPS} aria-hidden>
        <path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20V6.5Z" />
        <path d="M9 4v13.5M15 6.5V20" />
      </svg>
    ),
  },
  {
    id: 'satellite',
    label: 'Satelita',
    icon: (
      <svg {...ICON_PROPS} aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c2.6 2.5 3.9 5.5 3.9 9s-1.3 6.5-3.9 9c-2.6-2.5-3.9-5.5-3.9-9S9.4 5.5 12 3Z" />
      </svg>
    ),
  },
]

/** "Mapa / Satelita" switch stacked vertically above the zoom buttons, right edges aligned: two icon buttons the same size as the zoom buttons (40 px, enlarged in index.css). */
export default function BasemapSwitch({ basemap, onChange }: { basemap: Basemap; onChange: (b: Basemap) => void }) {
  return (
    <div
      className="pointer-events-auto absolute bottom-[210px] right-[10px] flex flex-col overflow-hidden rounded bg-white shadow-[0_0_0_2px_rgba(0,0,0,0.1)]"
      role="radiogroup"
      aria-label="Rodzaj mapy"
    >
      {OPTIONS.map((o) => (
        <button
          key={o.id}
          role="radio"
          aria-checked={basemap === o.id}
          aria-label={o.label}
          title={o.label}
          onClick={() => onChange(o.id)}
          className={`flex h-10 w-10 items-center justify-center transition first:border-b first:border-gray-200 ${
            basemap === o.id ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-100'
          }`}
        >
          {o.icon}
        </button>
      ))}
    </div>
  )
}
