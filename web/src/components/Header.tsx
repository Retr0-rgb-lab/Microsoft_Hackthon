import { useRef } from "react";
import { IconFolder, IconGear, IconSave } from "./icons";

type HeaderProps = {
  title: string;
  scheme: string;
  saveDisabled: boolean;
  onOpenVideo: (file: File) => void;
  onSave: () => void;
};

export function Header({ title, scheme, saveDisabled, onOpenVideo, onSave }: HeaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <header className="header">
      <div>
        <h1>{title}</h1>
        <p>{scheme}</p>
      </div>
      <div className="header-actions">
        <button type="button" className="icon-button" aria-label="Load a preview video" onClick={() => inputRef.current?.click()}>
          <IconFolder />
        </button>
        <input
          ref={inputRef}
          className="file-input"
          type="file"
          accept="video/mp4,video/*"
          aria-label="Preview video file"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) onOpenVideo(file);
          }}
        />
        <button type="button" className="icon-button" aria-label="Download the sidebar fixture" onClick={onSave} disabled={saveDisabled}>
          <IconSave />
        </button>
        <button type="button" className="icon-button" aria-label="Scheme A">
          <IconGear />
        </button>
      </div>
    </header>
  );
}
