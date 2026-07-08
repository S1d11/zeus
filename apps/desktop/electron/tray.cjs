// tray.cjs — System tray integration for Hermes desktop.
//
// Creates a system tray icon with a context menu that lets the user:
//   - Show/hide the main window
//   - Toggle the wake word listener ("Hey Hermes")
//   - Quit the app
//
// When the tray is active, closing the main window hides it to the tray
// instead of quitting the app (on all platforms, not just macOS).
// The app only truly quits via the tray's "Quit" menu item or
// app.quit() from elsewhere.
//
// Exports:
//   createTray(mainWindowRef, opts) → Tray
//     mainWindowRef: { get: () => BrowserWindow | null }
//     opts: { onQuit: () => void, onToggleWakeWord: () => boolean }
//       onToggleWakeWord is called when the user clicks the toggle;
//       it should return the new enabled state (true/false).
//   destroyTray()
//   showWindowFromTray()
//   updateTrayTooltip(text)
//   setWakeWordMenuItemEnabled(enabled)

"use strict";

const { Tray, Menu, nativeImage } = require("electron");
const path = require("path");
const fs = require("fs");

let tray = null;
let mainWindowRef = null;
let onQuitCallback = null;
let onToggleWakeWordCallback = null;
let wakeWordEnabled = false;
let defaultIcon = null;
let listeningIcon = null;

// ---------------------------------------------------------------------------
// Icon resolution
// ---------------------------------------------------------------------------

function resolveTrayIcon() {
  // On macOS, tray icons should be template images (monochrome).
  // On Windows/Linux, use the full-color icon.
  const appRoot = path.resolve(__dirname, "..");
  const candidates = [
    path.join(appRoot, "assets", "icon.ico"),
    path.join(appRoot, "assets", "icon.png"),
    path.join(appRoot, "public", "apple-touch-icon.png"),
    path.join(appRoot, "dist", "apple-touch-icon.png"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      try {
        const img = nativeImage.createFromPath(candidate);
        if (!img.isEmpty()) {
          // On macOS, mark as template for automatic dark/light adaptation
          if (process.platform === "darwin") {
            img.setTemplateImage(true);
          }
          return img;
        }
      } catch {
        // fall through to next candidate
      }
    }
  }
  return null;
}

/**
 * Create a "listening" variant of the tray icon by compositing a green
 * dot overlay in the bottom-right corner using raw RGBA pixel manipulation.
 * Falls back to the base icon if compositing fails.
 */
function createListeningIcon(baseIcon) {
  try {
    const size = baseIcon.getSize();
    const w = size.width || 16;
    const h = size.height || 16;

    // Get raw RGBA pixels from the base icon
    const rawData = baseIcon.toBitmap();
    if (!rawData || rawData.length < w * h * 4) return baseIcon;

    // Work on a copy of the pixel buffer
    const pixels = Buffer.from(rawData);

    // Draw a filled green circle in the bottom-right corner
    const dotRadius = Math.max(2, Math.round(Math.min(w, h) * 0.18));
    const cx = w - dotRadius - 1;
    const cy = h - dotRadius - 1;
    const r2 = dotRadius * dotRadius;

    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const dx = x - cx;
        const dy = y - cy;
        const dist2 = dx * dx + dy * dy;
        if (dist2 <= r2) {
          const idx = (y * w + x) * 4;
          // Green dot with full opacity
          pixels[idx] = 0x22;     // R
          pixels[idx + 1] = 0xc5; // G
          pixels[idx + 2] = 0x5e; // B
          pixels[idx + 3] = 0xff; // A
        }
      }
    }

    // Create a new image from the modified RGBA buffer
    const result = nativeImage.createFromBuffer(pixels, { width: w, height: h });
    if (result.isEmpty()) return baseIcon;
    return result;
  } catch {
    return baseIcon;
  }
}

// ---------------------------------------------------------------------------
// Window management helpers
// ---------------------------------------------------------------------------

function getMainWindow() {
  return mainWindowRef?.get?.() ?? null;
}

function showWindowFromTray() {
  const win = getMainWindow();
  if (!win || win.isDestroyed()) return;
  if (win.isMinimized()) win.restore();
  if (!win.isVisible()) win.show();
  win.focus();
}

function hideWindowToTray() {
  const win = getMainWindow();
  if (!win || win.isDestroyed()) return;
  win.hide();
}

function toggleWindowVisibility() {
  const win = getMainWindow();
  if (!win || win.isDestroyed()) return;
  if (win.isVisible() && win.isFocused()) {
    hideWindowToTray();
  } else {
    showWindowFromTray();
  }
}

// ---------------------------------------------------------------------------
// Context menu
// ---------------------------------------------------------------------------

function buildContextMenu() {
  const win = getMainWindow();
  const isVisible = win && !win.isDestroyed() && win.isVisible();

  return Menu.buildFromTemplate([
    {
      label: isVisible ? "Hide Hermes" : "Show Hermes",
      click: () => {
        if (isVisible) {
          hideWindowToTray();
        } else {
          showWindowFromTray();
        }
      },
    },
    { type: "separator" },
    {
      label: "Wake Word (\"Hey Hermes\")",
      type: "checkbox",
      checked: wakeWordEnabled,
      click: () => {
        if (onToggleWakeWordCallback) {
          wakeWordEnabled = onToggleWakeWordCallback();
        } else {
          wakeWordEnabled = !wakeWordEnabled;
        }
        // Rebuild menu to update the checkbox state
        if (tray) tray.setContextMenu(buildContextMenu());
      },
    },
    { type: "separator" },
    {
      label: "Quit Hermes",
      click: () => {
        if (onQuitCallback) onQuitCallback();
        // Force quit — the app.on("before-quit") handler cleans up
        const { app } = require("electron");
        app.quit();
      },
    },
  ]);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Create the system tray.
 *
 * @param {Object} ref - { get: () => BrowserWindow | null }
 * @param {Object} opts - { onQuit: Function, onToggleWakeWord: Function }
 * @returns {Tray|null}
 */
function createTray(ref, opts = {}) {
  mainWindowRef = ref;
  onQuitCallback = opts.onQuit || null;
  onToggleWakeWordCallback = opts.onToggleWakeWord || null;

  const icon = resolveTrayIcon();
  if (!icon) {
    console.error("[tray] No valid icon found, skipping tray creation");
    return null;
  }

  defaultIcon = icon;
  listeningIcon = createListeningIcon(icon);

  tray = new Tray(icon);
  tray.setToolTip("Hermes — click to show/hide");

  tray.on("click", () => {
    toggleWindowVisibility();
  });

  tray.on("right-click", () => {
    tray.popUpContextMenu(buildContextMenu());
  });

  // Set context menu (also accessible via right-click on some platforms)
  tray.setContextMenu(buildContextMenu());

  return tray;
}

function destroyTray() {
  if (tray) {
    tray.destroy();
    tray = null;
  }
}

function updateTrayTooltip(text) {
  if (tray) {
    tray.setToolTip(text);
  }
}

function setWakeWordMenuItemEnabled(enabled) {
  wakeWordEnabled = enabled;
  if (tray) {
    // Swap the tray icon to show a visual indicator when listening
    if (enabled && listeningIcon) {
      tray.setImage(listeningIcon);
    } else if (defaultIcon) {
      tray.setImage(defaultIcon);
    }
    tray.setContextMenu(buildContextMenu());
  }
}

module.exports = {
  createTray,
  destroyTray,
  showWindowFromTray,
  updateTrayTooltip,
  setWakeWordMenuItemEnabled,
};
