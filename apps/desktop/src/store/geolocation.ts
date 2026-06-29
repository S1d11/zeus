/**
 * Geolocation sync to the Python backend.
 *
 * Side-effect module: on import (from main.tsx), attempts to get the user's
 * approximate location via the HTML5 geolocation API and sends it to the
 * Electron main process, which writes it to ~/.hermes/location.json. The
 * agent's system prompt reads that file to include the user's location in
 * its context.
 *
 * This is fire-and-forget — if the user denies permission, the browser
 * doesn't support it, or the IPC call fails, we silently move on. The
 * location is refreshed on each app launch so it stays current when the
 * user moves.
 */

function syncLocation(): void {
  if (typeof window === 'undefined') { return }

  if (!('geolocation' in navigator)) { return }

  const bridge = (window as any).hermesDesktop

  if (!bridge?.updateLocation) { return }

  try {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude, accuracy } = pos.coords
        void bridge.updateLocation({ latitude, longitude, accuracy })
      },
      () => {
        // User denied or position unavailable — silently ignore.
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    )
  } catch {
    // Geolocation not available — silently ignore.
  }
}

syncLocation()
