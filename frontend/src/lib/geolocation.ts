import { KRAKOW_BBOX } from './dimensions'

/** Polish, actionable text for a failed position request (the browser's own reasons are cryptic or missing). */
export function geolocationErrorText(err: { code?: number } | null): string {
  if (typeof window !== 'undefined' && !window.isSecureContext) {
    return 'Lokalizacja działa tylko przez HTTPS lub localhost. Otwórz aplikację przez https:// albo localhost.'
  }
  switch (err?.code) {
    case 1:
      return 'Lokalizacja jest zablokowana. Kliknij ikonę kłódki przy adresie strony i zezwól na lokalizację.'
    case 2:
      return 'Nie można ustalić położenia. Włącz usługi lokalizacji w systemie (Windows: Ustawienia → Prywatność → Lokalizacja).'
    case 3:
      return 'Ustalanie lokalizacji trwa zbyt długo. Spróbuj ponownie.'
    default:
      return 'Nie udało się pobrać lokalizacji.'
  }
}

/** True when the point is inside the area the app serves (Krakow with a small margin). */
export function inServiceArea(lat: number, lon: number): boolean {
  const margin = 0.05
  return lon >= KRAKOW_BBOX[0] - margin && lat >= KRAKOW_BBOX[1] - margin && lon <= KRAKOW_BBOX[2] + margin && lat <= KRAKOW_BBOX[3] + margin
}

export const OUTSIDE_AREA_TEXT = 'Twoja lokalizacja jest poza obsługiwanym obszarem (Kraków).'

/** What a failed lookup says, as a thrown `Error`: its message is ready to show to the user. */
function fail(err: { code?: number } | null): never {
  throw new Error(geolocationErrorText(err))
}

function getPosition(options: PositionOptions): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, options))
}

/**
 * The user's position, for "Moja lokalizacja". A fast, low-accuracy fix first (network / Wi-Fi, a recent one may be reused):
 * computers without GPS often time out when high accuracy is demanded. Only if that fails for a reason other than a refusal,
 * high accuracy is tried. Rejects with an `Error` whose message is a Polish text for the user (also when outside Krakow).
 */
export async function locateUser(): Promise<{ lat: number; lon: number }> {
  if (!navigator.geolocation) throw new Error('Ta przeglądarka nie udostępnia lokalizacji.')
  let pos: GeolocationPosition
  try {
    pos = await getPosition({ enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 })
  } catch (first) {
    const code = (first as GeolocationPositionError).code
    if (code === 1 || !window.isSecureContext) fail(first as GeolocationPositionError)
    try {
      pos = await getPosition({ enableHighAccuracy: true, timeout: 20000, maximumAge: 0 })
    } catch (second) {
      fail(second as GeolocationPositionError)
    }
  }
  const { latitude: lat, longitude: lon } = pos.coords
  if (!inServiceArea(lat, lon)) throw new Error(OUTSIDE_AREA_TEXT)
  return { lat, lon }
}
