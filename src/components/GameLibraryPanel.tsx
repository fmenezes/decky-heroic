import {
  ButtonItem,
  Field,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  showModal,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { InstallModal } from "./InstallModal";
import {
  getHeroicStatus,
  openHeroicLauncher,
  primeLibrary,
  refreshHeroicStatus,
  subscribeHeroicStatus,
} from "../lib/heroic";
import {
  getSettingsSync,
  subscribeSettings,
  updateSetting,
  type PluginSettings,
} from "../lib/settings";
import { requestLibraryRerender } from "../patches/LibraryPatch";

export const GameLibraryPanel = () => {
  const [settings, setSettings] = useState<PluginSettings>(getSettingsSync());
  const [heroicStatus, setHeroicStatus] = useState(getHeroicStatus());
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const unsub = subscribeSettings(setSettings);
    const unsubStatus = subscribeHeroicStatus(() =>
      setHeroicStatus(getHeroicStatus()),
    );
    void refreshHeroicStatus();
    return () => {
      unsub();
      unsubStatus();
    };
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshHeroicStatus();
      await primeLibrary();
      requestLibraryRerender();
      toaster.toast({
        title: "Heroic Library",
        body: "Library and accounts refreshed",
      });
    } catch (e: any) {
      toaster.toast({
        title: "Heroic Library",
        body: `Refresh failed: ${e?.message || e}`,
      });
    } finally {
      setRefreshing(false);
    }
  };

  const handleOpenInstallModal = () => {
    let modalHandle: { Close: () => void } | undefined;
    modalHandle = showModal(
      <InstallModal
        closeModal={() => modalHandle?.Close()}
        onSuccess={() => void refreshHeroicStatus()}
      />,
    );
  };

  // State 1: Heroic is not installed -> show only install button
  if (!heroicStatus.installed) {
    return (
      <PanelSection title="Heroic Library">
        <PanelSectionRow>
          <div
            style={{
              color: "#e0654b",
              fontSize: "13px",
              fontWeight: "bold",
              marginBottom: "4px",
            }}
          >
            Heroic is not installed
          </div>
          <div
            style={{
              color: "#d0d0d0",
              fontSize: "12px",
              marginBottom: "8px",
            }}
          >
            Heroic Games Launcher is required to sync and launch games from Epic
            Games, GOG, and Amazon Prime.
          </div>
          {heroicStatus.hasFlatpak ? (
            <ButtonItem
              layout="below"
              bottomSeparator="none"
              onClick={handleOpenInstallModal}
            >
              Install Heroic (Flatpak)
            </ButtonItem>
          ) : (
            <div style={{ color: "#e0654b", fontSize: "12px" }}>
              Flatpak is not available on this system. Please install Heroic
              Games Launcher manually.
            </div>
          )}
        </PanelSectionRow>
      </PanelSection>
    );
  }

  // State 2: Heroic is installed -> show open button and tab controls
  return (
    <PanelSection title="Heroic Library">
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          bottomSeparator="none"
          onClick={() => void openHeroicLauncher().catch(console.error)}
        >
          Open Heroic Games Launcher
        </ButtonItem>
      </PanelSectionRow>

      <PanelSectionRow>
        <ButtonItem
          layout="below"
          bottomSeparator="standard"
          disabled={refreshing}
          onClick={() => void handleRefresh()}
        >
          {refreshing ? "Refreshing…" : "Refresh Library & Accounts"}
        </ButtonItem>
      </PanelSectionRow>

      {heroicStatus.warnings && heroicStatus.warnings.length > 0 && (
        <PanelSection title="Heroic Configuration Warnings">
          {heroicStatus.warnings.map((w) => (
            <PanelSectionRow key={w.id}>
              <div
                style={{
                  background: "rgba(245, 166, 35, 0.12)",
                  borderLeft: "4px solid #f5a623",
                  padding: "8px 12px",
                  borderRadius: "2px",
                  width: "100%",
                  boxSizing: "border-box",
                  marginBottom: "4px",
                }}
              >
                <div
                  style={{
                    color: "#f5a623",
                    fontWeight: "bold",
                    fontSize: "12px",
                    marginBottom: "4px",
                  }}
                >
                  {w.title}
                </div>
                <div
                  style={{
                    color: "#d0d0d0",
                    fontSize: "11px",
                    lineHeight: "1.4",
                  }}
                >
                  {w.message}
                </div>
              </div>
            </PanelSectionRow>
          ))}
        </PanelSection>
      )}

      <PanelSectionRow>
        <div style={{ opacity: "0.6", fontSize: "12px" }}>
          Active store libraries appear as tabs in the Steam library. Opening a
          game registers it as a native Steam shortcut.
        </div>
      </PanelSectionRow>

      <PanelSectionRow>
        {heroicStatus.stores.gog ? (
          <ToggleField
            label="GOG library tab"
            description="Show GOG games as a tab in the Steam library"
            checked={settings.gogTab}
            onChange={(v) => void updateSetting("gogTab", v)}
          />
        ) : (
          <Field
            label="GOG library tab"
            description={
              <span style={{ color: "#f5a623" }}>
                Not logged in — sign in via Heroic first
              </span>
            }
            disabled
          />
        )}
      </PanelSectionRow>

      <PanelSectionRow>
        {heroicStatus.stores.epic ? (
          <ToggleField
            label="Epic library tab"
            description="Show Epic games as a tab in the Steam library"
            checked={settings.epicTab}
            onChange={(v) => void updateSetting("epicTab", v)}
          />
        ) : (
          <Field
            label="Epic library tab"
            description={
              <span style={{ color: "#f5a623" }}>
                Not logged in — sign in via Heroic first
              </span>
            }
            disabled
          />
        )}
      </PanelSectionRow>

      <PanelSectionRow>
        {heroicStatus.stores.amazon ? (
          <ToggleField
            label="Amazon library tab"
            description="Show Amazon games as a tab in the Steam library"
            checked={settings.amazonTab}
            onChange={(v) => void updateSetting("amazonTab", v)}
          />
        ) : (
          <Field
            label="Amazon library tab"
            description={
              <span style={{ color: "#f5a623" }}>
                Not logged in — sign in via Heroic first
              </span>
            }
            disabled
          />
        )}
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label="Sideloaded library tab"
          description="Show sideloaded games as a tab in the Steam library"
          checked={settings.sideloadTab}
          onChange={(v) => void updateSetting("sideloadTab", v)}
        />
      </PanelSectionRow>
    </PanelSection>
  );
};
