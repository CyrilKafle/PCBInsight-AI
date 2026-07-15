import { useRef, useState, type ChangeEvent, type DragEvent } from "react";

interface UploadZoneProps {
  onFilesSelected: (files: File[]) => void;
  disabled?: boolean;
}

export function UploadZone({ onFilesSelected, disabled }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const folderInputRef = useRef<HTMLInputElement>(null);

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) onFilesSelected(files);
  }

  function handleFolderPick(event: ChangeEvent<HTMLInputElement>) {
    const files = event.target.files ? Array.from(event.target.files) : [];
    if (files.length > 0) onFilesSelected(files);
    event.target.value = "";
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className={`rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
        isDragging ? "border-blue-500 bg-blue-500/5" : "border-neutral-700"
      } ${disabled ? "opacity-50" : ""}`}
    >
      <p className="font-medium text-neutral-300">Drag KiCad project files here</p>
      <p className="mt-1 text-sm text-neutral-500">.kicad_pcb, .kicad_pro, and related files</p>
      <div className="mt-4">
        <button
          type="button"
          disabled={disabled}
          onClick={() => folderInputRef.current?.click()}
          className="rounded-md bg-neutral-800 px-4 py-2 text-sm font-medium text-neutral-100 hover:bg-neutral-700 disabled:cursor-not-allowed"
        >
          Or select a project folder
        </button>
        <input
          ref={folderInputRef}
          type="file"
          // webkitdirectory is a non-standard but widely supported (Chromium)
          // attribute for picking a whole folder; not in React's JSX types.
          // eslint-disable-next-line @typescript-eslint/ban-ts-comment
          // @ts-expect-error -- see comment above
          webkitdirectory=""
          multiple
          hidden
          onChange={handleFolderPick}
        />
      </div>
    </div>
  );
}
