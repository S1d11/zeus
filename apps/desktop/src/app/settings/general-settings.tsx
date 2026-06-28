// general-settings.tsx — General settings tab for Zeus desktop.
//
// Houses app-wide preferences:
//   - Auto-launch on startup
//   - Start minimized to tray
//   - Close to tray (vs fully quit)
//   - Minimize to tray (vs taskbar)
//   - Wake word ("Hey Zeus") enable/disable
//   - Automatic update checks

import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { Switch } from '@/components/ui/switch'
import { useI18n } from '@/i18n'
import { triggerHaptic } from '@/lib/haptics'
import { Settings2 } from '@/lib/icons'
import { cn } from '@/lib/utils'
import {
  $generalPrefs,
  setAutoLaunchOnStartup,
  setCheckForUpdatesAutomatically,
  setCloseToTray,
  setMinimizeToTray,
  setStartMinimized,
  setWakeWordEnabled,
} from '@/store/general-settings'

import { ListRow, SectionHeading, SettingsContent } from './primitives'

const CAPTION = 'text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)'

function Caption({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn(CAPTION, className)}>{children}</p>
}

function ToggleRow(props: {
  checked: boolean
  description: string
  disabled?: boolean
  label: string
  onChange: (on: boolean) => void
}) {
  return (
    <ListRow
      action={
        <Switch
          aria-label={props.label}
          checked={props.checked}
          disabled={props.disabled}
          onCheckedChange={on => {
            triggerHaptic('selection')
            props.onChange(on)
          }}
        />
      }
      description={props.description}
      title={props.label}
    />
  )
}

export function GeneralSettings() {
  const { t } = useI18n()
  const prefs = useStore($generalPrefs)
  const copy = t.settings.general
  const [wakeWordListening, setWakeWordListening] = useState(false)

  // Check actual wake word listener status on mount
  useEffect(() => {
    const desktop = window.hermesDesktop as any
    if (!desktop?.zeus?.getWakeWordStatus) return
    desktop.zeus.getWakeWordStatus().then((status: { listening: boolean }) => {
      setWakeWordListening(status.listening)
    })
  }, [])

  const handleWakeWordToggle = (on: boolean) => {
    setWakeWordEnabled(on)
    setWakeWordListening(on)
  }

  return (
    <SettingsContent>
      <SectionHeading icon={Settings2} title={copy.title} />
      <Caption className="mb-2 leading-(--conversation-caption-line-height)">{copy.intro}</Caption>

      {/* --- Startup --- */}
      <div className="mt-4 mb-1 text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary) uppercase tracking-wide">
        {copy.startupSection}
      </div>

      <ToggleRow
        checked={prefs.autoLaunchOnStartup}
        description={copy.autoLaunchDesc}
        label={copy.autoLaunch}
        onChange={setAutoLaunchOnStartup}
      />

      <ToggleRow
        checked={prefs.startMinimized}
        description={copy.startMinimizedDesc}
        disabled={!prefs.autoLaunchOnStartup}
        label={copy.startMinimized}
        onChange={setStartMinimized}
      />

      <div className="my-1 h-px bg-border/30" />

      {/* --- Window behavior --- */}
      <div className="mt-2 mb-1 text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary) uppercase tracking-wide">
        {copy.windowSection}
      </div>

      <ToggleRow
        checked={prefs.closeToTray}
        description={copy.closeToTrayDesc}
        label={copy.closeToTray}
        onChange={setCloseToTray}
      />

      <ToggleRow
        checked={prefs.minimizeToTray}
        description={copy.minimizeToTrayDesc}
        label={copy.minimizeToTray}
        onChange={setMinimizeToTray}
      />

      <div className="my-1 h-px bg-border/30" />

      {/* --- Voice --- */}
      <div className="mt-2 mb-1 text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary) uppercase tracking-wide">
        {copy.voiceSection}
      </div>

      <ToggleRow
        checked={wakeWordListening}
        description={copy.wakeWordDesc}
        label={copy.wakeWord}
        onChange={handleWakeWordToggle}
      />

      <div className="my-1 h-px bg-border/30" />

      {/* --- Updates --- */}
      <div className="mt-2 mb-1 text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary) uppercase tracking-wide">
        {copy.updatesSection}
      </div>

      <ToggleRow
        checked={prefs.checkForUpdatesAutomatically}
        description={copy.autoUpdatesDesc}
        label={copy.autoUpdates}
        onChange={setCheckForUpdatesAutomatically}
      />
    </SettingsContent>
  )
}
