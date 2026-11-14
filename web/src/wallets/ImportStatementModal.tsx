import { Alert, Button, FileInput, Group, Modal, ScrollArea, Stack, Table, Text } from "@mantine/core";
import { IconFileTypeCsv } from "@tabler/icons-react";
import { useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { importDegiro, type ImportResponse, previewDegiroImport, type WalletResponse } from "../api/generated";
import { formatDate } from "../ui/format";
import { Money } from "../ui/Money";
import { DIALOG_LIST_MAX_HEIGHT, ICON_SIZE } from "../ui/theme";

type Props = {
  wallet: WalletResponse | null; // the wallet to import into; null when closed
  onClose: () => void;
  onImported: () => void;
};

const CSV = ".csv,text/csv";

/** Import a DEGIRO statement: pick its two exports, preview what the wallet would become, then import. */
export function ImportStatementModal({ wallet, onClose, onImported }: Props) {
  return (
    <Modal opened={wallet !== null} onClose={onClose} title="Import from DEGIRO" size="lg">
      {/* Keyed by wallet, so the dialog starts fresh for each one. */}
      {wallet && <ImportForm key={wallet.id} wallet={wallet} onClose={onClose} onImported={onImported} />}
    </Modal>
  );
}

function ImportForm({ wallet, onClose, onImported }: { wallet: WalletResponse; onClose: () => void; onImported: () => void }) {
  const [transactions, setTransactions] = useState<File | null>(null);
  const [account, setAccount] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResponse | null>(null);
  const [busy, setBusy] = useState<"preview" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A changed file makes the preview stale.
  function choose(set: (file: File | null) => void) {
    return (file: File | null) => {
      set(file);
      setPreview(null);
      setError(null);
    };
  }

  async function send(save: boolean) {
    if (!transactions || !account) {
      return;
    }
    setBusy(save ? "import" : "preview");
    setError(null);
    try {
      const options = { path: { wallet_id: wallet.id }, body: { transactions: await transactions.text(), account: await account.text() } };
      const { data, error } = await (save ? importDegiro(options) : previewDegiroImport(options));
      if (!data) {
        setError(apiErrorMessage(error));
      } else if (save && data.imported) {
        onClose();
        onImported();
      } else {
        setPreview(data);
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        In DEGIRO, export the Transactions and the Account statement (CSV) for the whole period. Nothing is saved until you import.
      </Text>
      <FileInput label="Transactions export" accept={CSV} leftSection={<IconFileTypeCsv size={ICON_SIZE} />} value={transactions} onChange={choose(setTransactions)} clearable />
      <FileInput label="Account export" accept={CSV} leftSection={<IconFileTypeCsv size={ICON_SIZE} />} value={account} onChange={choose(setAccount)} clearable />
      {error && <Alert color="red">{error}</Alert>}
      {preview && <Preview preview={preview} currency={wallet.currency} />}
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>
          Cancel
        </Button>
        {/* Preview first; the import is offered once the preview shows it can go in. */}
        {preview?.can_import ? (
          <Button loading={busy === "import"} onClick={() => send(true)}>
            Import
          </Button>
        ) : (
          <Button loading={busy === "preview"} disabled={!transactions || !account} onClick={() => send(false)}>
            Preview
          </Button>
        )}
      </Group>
      {busy && (
        <Text size="sm" c="dimmed">
          This can take a minute: tickers and splits are looked up for every security.
        </Text>
      )}
    </Stack>
  );
}

function Preview({ preview, currency }: { preview: ImportResponse; currency: string }) {
  const holdings = Object.entries(preview.holdings);
  if (!preview.can_import) {
    return (
      <Alert color="red" title={`${preview.problems.length} of ${preview.records} rows cannot be imported, so nothing will be`}>
        <ScrollArea.Autosize mah={DIALOG_LIST_MAX_HEIGHT}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Date</Table.Th>
                <Table.Th>Row</Table.Th>
                <Table.Th>Problem</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {preview.problems.map((problem, index) => (
                <Table.Tr key={index}>
                  <Table.Td>{formatDate(problem.date)}</Table.Td>
                  <Table.Td>{problem.description}</Table.Td>
                  <Table.Td>{problem.reason}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea.Autosize>
      </Alert>
    );
  }
  return (
    <Alert color="teal" title={`All ${preview.records} rows can be imported`}>
      <Stack gap="xs">
        <Text size="sm">
          After the import: <Money amount={preview.cash} currency={currency} /> in cash
          {holdings.length === 0 ? " and no holdings." : ", and these holdings:"}
        </Text>
        {holdings.length > 0 && (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Symbol</Table.Th>
                <Table.Th ta="right">Shares</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {holdings.map(([symbol, shares]) => (
                <Table.Tr key={symbol}>
                  <Table.Td>{symbol}</Table.Td>
                  <Table.Td ta="right">{shares}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Stack>
    </Alert>
  );
}
