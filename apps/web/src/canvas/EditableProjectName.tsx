import { useRef, useState } from "react";
import { Pencil } from "lucide-react";

export interface EditableProjectNameProps {
  value: string;
  onCommit(value: string): Promise<void> | void;
}

export function EditableProjectName({ value, onCommit }: EditableProjectNameProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const committingRef = useRef(false);

  const beginEditing = () => {
    setDraft(value);
    setEditing(true);
  };

  const cancelEditing = () => {
    setDraft(value);
    setEditing(false);
  };

  const commitEditing = async () => {
    if (committingRef.current) return;
    const nextValue = draft.trim();
    if (nextValue.length === 0 || nextValue === value) {
      cancelEditing();
      return;
    }
    committingRef.current = true;
    setSaving(true);
    try {
      await onCommit(nextValue);
      setEditing(false);
    } finally {
      committingRef.current = false;
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <input
        className="canvas-file-name-input"
        aria-label="File name"
        aria-busy={saving}
        autoFocus
        autoComplete="off"
        disabled={saving}
        maxLength={200}
        spellCheck={false}
        value={draft}
        onBlur={() => void commitEditing()}
        onChange={(event) => setDraft(event.currentTarget.value)}
        onFocus={(event) => event.currentTarget.select()}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void commitEditing();
          } else if (event.key === "Escape") {
            event.preventDefault();
            cancelEditing();
          }
        }}
      />
    );
  }

  return (
    <button className="canvas-file-name" type="button" onClick={beginEditing} title="Edit file name">
      <span>{value}</span>
      <Pencil size={12} aria-hidden />
    </button>
  );
}
