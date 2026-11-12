import { ActionIcon, Group, TextInput, Title } from "@mantine/core";
import { IconPencil } from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";

import { ICON_SIZE } from "./theme";

type Props = {
  value: string;
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
  /** Saves the new value; resolves to an error message, or null when it worked. */
  onSave: (value: string) => Promise<string | null>;
  label: string; // what is being edited, for screen readers, e.g. "Wallet name"
};

/**
 * A page title that can be edited in place: the pencil (or `editing`) turns it into a text field.
 * Enter or leaving the field saves; Esc cancels. On error the field stays open with the message.
 */
export function EditableTitle({ value, editing, onEditingChange, onSave, label }: Props) {
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Refs, so Enter followed by the field losing focus does not save twice, and Esc does not save.
  const busy = useRef(false);
  const cancelled = useRef(false);

  useEffect(() => {
    if (editing) {
      setDraft(value);
      setError(null);
      cancelled.current = false;
    }
  }, [editing, value]);

  async function save() {
    if (busy.current || cancelled.current) {
      return;
    }
    if (draft === value) {
      onEditingChange(false);
      return;
    }
    busy.current = true;
    setSaving(true);
    const message = await onSave(draft);
    busy.current = false;
    setSaving(false);
    if (message) {
      setError(message);
    } else {
      onEditingChange(false);
    }
  }

  function cancel() {
    cancelled.current = true;
    onEditingChange(false);
  }

  if (!editing) {
    return (
      <Group gap="xs" wrap="nowrap">
        <Title order={1}>{value}</Title>
        <ActionIcon variant="subtle" color="gray" aria-label={`Edit ${label.toLowerCase()}`} onClick={() => onEditingChange(true)}>
          <IconPencil size={ICON_SIZE} />
        </ActionIcon>
      </Group>
    );
  }
  return (
    <TextInput
      size="lg"
      aria-label={label}
      autoFocus
      value={draft}
      disabled={saving}
      error={error}
      onFocus={(event) => event.currentTarget.select()}
      onChange={(event) => setDraft(event.currentTarget.value)}
      onBlur={save}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          void save();
        } else if (event.key === "Escape") {
          cancel();
        }
      }}
    />
  );
}
