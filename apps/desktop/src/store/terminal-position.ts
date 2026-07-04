/**
 * Terminal panel position preference.
 *
 * Controls where the terminal pane docks in the desktop layout:
 *  - `auto`   → side panel when the rail is empty, bottom row when another
 *               rail pane (preview / file browser / review) is open (default,
 *               preserves the original automatic behaviour)
 *  - `side`   → always dock as a side column, even when the rail is crowded
 *  - `bottom` → always dock as a full-width bottom row
 *
 * The value persists across relaunches via localStorage.
 */

import { atom } from 'nanostores'

import { persistString, storedString } from '@/lib/storage'

const KEY = 'hermes.desktop.terminalPosition.v1'

export type TerminalPosition = 'auto' | 'side' | 'bottom'

const VALID: readonly TerminalPosition[] = ['auto', 'side', 'bottom']

const read = (): TerminalPosition => {
  const raw = storedString(KEY)

  return raw && (VALID as readonly string[]).includes(raw) ? (raw as TerminalPosition) : 'auto'
}

export const $terminalPosition = atom<TerminalPosition>(typeof window === 'undefined' ? 'auto' : read())

export function setTerminalPosition(position: TerminalPosition): void {
  $terminalPosition.set(position)
}

if (typeof window !== 'undefined') {
  $terminalPosition.subscribe(position => persistString(KEY, position))
}
