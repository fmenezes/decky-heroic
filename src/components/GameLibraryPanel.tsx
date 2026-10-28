import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
} from "@decky/ui";
import { useEffect, useState } from "react";
import {
  getHeroicStatus,
  openHeroicLauncher,
  refreshHeroicStatus,
  subscribeHeroicStatus,
} from "../lib/heroic";
import {
  getSettingsSync,
  subscribeSettings,
  updateSetting,
  type PluginSettings,
} from "../lib/settings";

export const GameLibraryPanel = () => {
  const [settings, setSettings] = useState<PluginSettings>(getSettingsSync());
  const [heroicStatus, setHeroicStatus] = useState(getHeroicStatus());

  useEffect(() => {
    const unsub = subscribeSettings(setSettings);
    const unsubStatus = subscribeHeroicStatus(() =>
      setHeroicStatus(getHeroicStatus()),
    );
    return () => {
      unsub();
      unsubStatus();
    };
  }, []);

  const onConfigPath = (e: React.ChangeEvent<HTMLInputElement>) => {
    void updateSetting("configPath", e.target.value).then(() =>
      refreshHeroicStatus(),
    );
  };

  return (
    <PanelSection title="Heroic Library">
      {!heroicStatus.found && (
        <PanelSectionRow>
          <div
            style={{
              color: "#e0654b",
              fontSize: "13px",
              fontWeight: "bold",
            }}
          >
            Heroic not found
          </div>
          <div style={{ color: "#e0654b", fontSize: "12px" }}>
            Looked in: {heroicStatus.probed.join("; ") || "nowhere"}. Set the
            config folder below to point the plugin at your Heroic install.
          </div>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <div style={{ opacity: "0.6", fontSize: "12px" }}>
          GOG, Epic, Amazon and Sideloaded games appear as tabs in the Steam
          library. Opening a game from there registers it as a native Steam
          shortcut.
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="GOG library tab"
          description="Show GOG games as a tab in the Steam library"
          checked={settings.gogTab}
          onChange={(v) => void updateSetting("gogTab", v)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Epic library tab"
          description="Show Epic games as a tab in the Steam library"
          checked={settings.epicTab}
          onChange={(v) => void updateSetting("epicTab", v)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Amazon library tab"
          description="Show Amazon games as a tab in the Steam library"
          checked={settings.amazonTab}
          onChange={(v) => void updateSetting("amazonTab", v)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Sideloaded library tab"
          description="Show sideloaded games as a tab in the Steam library"
          checked={settings.sideloadTab}
          onChange={(v) => void updateSetting("sideloadTab", v)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          label="Heroic config folder"
          description="Only needed if auto-detection fails (e.g. a non-standard install location)"
          value={settings.configPath}
          onChange={onConfigPath}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          bottomSeparator="none"
          onClick={() => void openHeroicLauncher().catch(console.error)}
        >
          Heroic Games Launcher
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
};
