import {
  DialogBody,
  DialogButton,
  DialogFooter,
  DialogHeader,
  ModalRoot,
  Spinner,
} from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import {
  getInstallProgress,
  refreshHeroicStatus,
  startInstallHeroic,
  type InstallProgress,
} from "../lib/heroic";

interface Props {
  closeModal?: () => void;
  onSuccess?: () => void;
}

export const InstallModal = ({ closeModal, onSuccess }: Props) => {
  const [progress, setProgress] = useState<InstallProgress>({
    status: "running",
    logs: [],
  });
  const logsEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void startInstallHeroic().then((initial) => {
      setProgress(initial);
    });

    const interval = setInterval(async () => {
      try {
        const current = await getInstallProgress();
        setProgress(current);
        if (current.status === "success") {
          clearInterval(interval);
          void refreshHeroicStatus().then(() => {
            onSuccess?.();
          });
        } else if (current.status === "error") {
          clearInterval(interval);
        }
      } catch (e) {
        console.error("Failed to query install progress:", e);
      }
    }, 500);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [progress.logs]);

  const isRunning = progress.status === "running";
  const isSuccess = progress.status === "success";
  const isError = progress.status === "error";

  return (
    <ModalRoot
      closeModal={isRunning ? undefined : closeModal}
      bDisableBackgroundDismiss={isRunning}
    >
      <DialogHeader>Installing Heroic Games Launcher</DialogHeader>
      <DialogBody>
        <div
          style={{
            marginBottom: "10px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "13px",
          }}
        >
          {isRunning && <Spinner style={{ width: "16px", height: "16px" }} />}
          {isRunning && <span>Downloading and installing from Flathub…</span>}
          {isSuccess && (
            <span style={{ color: "#4caf50", fontWeight: "bold" }}>
              ✓ Heroic installed successfully!
            </span>
          )}
          {isError && (
            <span style={{ color: "#e0654b", fontWeight: "bold" }}>
              ✕ Installation failed: {progress.error || "Unknown error"}
            </span>
          )}
        </div>

        <div
          ref={containerRef}
          style={{
            backgroundColor: "#0d1117",
            color: "#c9d1d9",
            padding: "10px",
            borderRadius: "6px",
            fontFamily: "monospace",
            fontSize: "11px",
            lineHeight: "1.4",
            height: "220px",
            overflowY: "auto",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}
        >
          {progress.logs.length === 0 ? (
            <div style={{ opacity: 0.5 }}>Waiting for Flatpak output…</div>
          ) : (
            progress.logs.map((line, idx) => (
              <div key={idx} style={{ marginBottom: "2px" }}>
                {line}
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </DialogBody>
      <DialogFooter>
        <DialogButton disabled={isRunning} onClick={closeModal}>
          {isRunning ? "Installing…" : "Close"}
        </DialogButton>
      </DialogFooter>
    </ModalRoot>
  );
};
