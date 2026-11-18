import { Button, Group, Title, Tooltip } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconPlus } from "@tabler/icons-react";
import { useCallback, useEffect, useState } from "react";

import { newWalletBlocked, useMe } from "../account/plan";
import { listWallets, type WalletResponse } from "../api/generated";
import { ICON_SIZE } from "../ui/theme";
import { CreateWalletModal } from "./CreateWalletModal";
import { DeleteWalletsModal } from "./DeleteWalletsModal";
import { DuplicateWalletModal } from "./DuplicateWalletModal";
import { RenameWalletModal } from "./RenameWalletModal";
import { WalletSettingsModal } from "./WalletSettingsModal";
import { ImportStatementModal } from "./ImportStatementModal";
import { WalletSelectionBar } from "./WalletSelectionBar";
import { WalletTable } from "./WalletTable";

/** The list of the user's wallets. */
export function WalletsPage() {
  const [wallets, setWallets] = useState<WalletResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [creating, { open: openCreate, close: closeCreate }] = useDisclosure(false);
  const [toRename, setToRename] = useState<WalletResponse | null>(null);
  const [toConfigure, setToConfigure] = useState<WalletResponse | null>(null);
  const [toImportInto, setToImportInto] = useState<WalletResponse | null>(null);
  const [toDuplicate, setToDuplicate] = useState<WalletResponse | null>(null);
  const [toDelete, setToDelete] = useState<WalletResponse[]>([]);

  const loadWallets = useCallback(() => {
    listWallets()
      .then(({ data }) => {
        if (!data) {
          setError("Could not load wallets.");
          return;
        }
        setWallets(data);
        // Forget selected wallets that no longer exist.
        setSelectedIds((ids) => new Set(data.filter((wallet) => ids.has(wallet.id)).map((wallet) => wallet.id)));
      })
      .catch(() => setError("Could not reach the backend."));
  }, []);

  useEffect(loadWallets, [loadWallets]);

  const selected = (wallets ?? []).filter((wallet) => selectedIds.has(wallet.id));
  const blocked = newWalletBlocked(useMe(), wallets && wallets.length);

  return (
    <>
      <Group justify="space-between" mb="lg">
        <Title order={1}>Wallets</Title>
        <Tooltip label={blocked} disabled={blocked === null}>
          {/* The wrapper keeps the tooltip working while the button is disabled. */}
          <span>
            <Button leftSection={<IconPlus size={ICON_SIZE} />} onClick={openCreate} disabled={blocked !== null}>
              New wallet
            </Button>
          </span>
        </Tooltip>
      </Group>
      <WalletSelectionBar selected={selected} duplicateBlocked={blocked} onDuplicate={setToDuplicate} onDelete={setToDelete} onClear={() => setSelectedIds(new Set())} />
      <WalletTable
        wallets={wallets}
        error={error}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
        onRename={setToRename}
        onSettings={setToConfigure}
        onImport={setToImportInto}
        onDuplicate={setToDuplicate}
        duplicateBlocked={blocked}
        onDelete={setToDelete}
      />
      <CreateWalletModal opened={creating} onClose={closeCreate} onCreated={loadWallets} />
      <RenameWalletModal wallet={toRename} onClose={() => setToRename(null)} onRenamed={loadWallets} />
      <WalletSettingsModal wallet={toConfigure} onClose={() => setToConfigure(null)} onSaved={loadWallets} />
      <ImportStatementModal wallet={toImportInto} onClose={() => setToImportInto(null)} onImported={loadWallets} />
      <DuplicateWalletModal wallet={toDuplicate} onClose={() => setToDuplicate(null)} onDuplicated={loadWallets} />
      <DeleteWalletsModal wallets={toDelete} onClose={() => setToDelete([])} onDeleted={loadWallets} />
    </>
  );
}
