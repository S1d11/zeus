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

import { SectionHeading, SettingsContent } from './primitives'

const CAPTION = 'text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)'

function Caption({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn(CAPTION, className)}>{children}</p>
}

/** A card that groups related settings with a header label. */
function SettingsCard({
  label,
  children
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) overflow-hidden">
      <div className="px-4 pt-3 pb-1 text-xs font-semibold text-(--ui-text-secondary) uppercase tracking-wide">
        {label}
      </div>
      <div className="divide-y divide-(--ui-stroke-secondary)/50">{children}</div>
    </div>
  )
}

/** A single toggle row inside a settings card. */
function ToggleRow(props: {
  checked: boolean
  description: string
  disabled?: boolean
  label: string
  onChange: (on: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-foreground">{props.label}</div>
        <div className="mt-0.5 text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
          {props.description}
        </div>
      </div>
      <Switch
        aria-label={props.label}
        checked={props.checked}
        disabled={props.disabled}
        onCheckedChange={on => {
          triggerHaptic('selection')
          props.onChange(on)
        }}
      />
    </div>
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
      <Caption className="mb-4 leading-(--conversation-caption-line-height)">{copy.intro}</Caption>

      <div className="flex flex-col gap-3">
        {/* --- Startup --- */}
        <SettingsCard label={copy.startupSection}>
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
        </SettingsCard>

        {/* --- Window behavior --- */}
        <SettingsCard label={copy.windowSection}>
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
        </SettingsCard>

        {/* --- Voice --- */}
        <SettingsCard label={copy.voiceSection}>
          <ToggleRow
            checked={wakeWordListening}
            description={copy.wakeWordDesc}
            label={copy.wakeWord}
            onChange={handleWakeWordToggle}
          />
        </SettingsCard>

        {/* --- Updates --- */}
        <SettingsCard label={copy.updatesSection}>
          <ToggleRow
            checked={prefs.checkForUpdatesAutomatically}
            description={copy.autoUpdatesDesc}
            label={copy.autoUpdates}
            onChange={setCheckForUpdatesAutomatically}
          />
        </SettingsCard>
      </div>
    </SettingsContent>
  )
}
