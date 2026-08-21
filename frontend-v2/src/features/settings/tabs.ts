export const SETTINGS_TABS = ["account", "usage", "models", "tools", "browser", "appearance"] as const
export type SettingsTab = (typeof SETTINGS_TABS)[number]
