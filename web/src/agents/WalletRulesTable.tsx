import { Anchor, Button, Stack, Table, Text, Title } from "@mantine/core";
import { Link } from "react-router";

import type { WalletResponse } from "../api/generated";
import { walletPath } from "../routes";
import { shiftDecimal } from "../ui/format";
import { TABLE_MIN_WIDTH } from "../ui/theme";

// A share of the wallet's value (0.2) as a percentage (20%).
const PERCENT_PLACES = 2;
const NO_LIMIT = "No limit";

type Props = { wallets: WalletResponse[]; onEdit: (wallet: WalletResponse) => void };

/**
 * Each wallet's rules for orders, where its agents' tokens are managed: the limits an agent trades within. Edited in
 * the wallet's settings, as everywhere else.
 */
export function WalletRulesTable({ wallets, onEdit }: Props) {
  return (
    <Stack gap="xs">
      <Title order={2}>Each wallet&apos;s rules</Title>
      <Text c="dimmed">
        Every order placed in a wallet, by an agent or by you, is checked against its rules, and refused with the reason
        when it would break one.
      </Text>
      <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Wallet</Table.Th>
              <Table.Th>Largest position</Table.Th>
              <Table.Th>Cash to keep</Table.Th>
              <Table.Th>Orders a month</Table.Th>
              <Table.Th>Symbols it may buy</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {wallets.map((wallet) => {
              const rules = wallet.rules;
              return (
                <Table.Tr key={wallet.id}>
                  <Table.Td>
                    <Anchor component={Link} to={walletPath(wallet.id)}>
                      {wallet.name}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>{percent(rules.max_position_weight)}</Table.Td>
                  <Table.Td>{percent(rules.min_cash_weight)}</Table.Td>
                  <Table.Td>{rules.max_orders_per_month ?? NO_LIMIT}</Table.Td>
                  <Table.Td>{rules.allowed_symbols.length > 0 ? rules.allowed_symbols.join(", ") : "Any"}</Table.Td>
                  <Table.Td ta="right">
                    <Button size="xs" variant="subtle" onClick={() => onEdit(wallet)}>
                      Edit rules
                    </Button>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  );
}

function percent(ratio: string | null | undefined): string {
  return ratio == null ? NO_LIMIT : `${shiftDecimal(ratio, PERCENT_PLACES)}%`;
}
