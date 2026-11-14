import { Group, SegmentedControl } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconCalendar } from "@tabler/icons-react";

import { DATE_INPUT_FORMAT, parseDateInput } from "../ui/format";
import { DATE_INPUT_WIDTH, ICON_SIZE } from "../ui/theme";
import { type DayRange, Period } from "./period";

type Props = { period: Period | null; range: DayRange; onChoose: (choice: Period | DayRange) => void };

/** A preset period, or dates typed or picked: as in Grafana's and Google Analytics' period pickers. */
export function PeriodControls({ period, range, onChoose }: Props) {
  const backwards = range.start !== null && range.end !== null && range.start > range.end;
  return (
    <Group gap="xs" align="flex-start">
      <SegmentedControl size="xs" aria-label="Period" data={Object.values(Period)} value={period ?? ""} onChange={(value) => onChoose(value as Period)} />
      <DayInput label="From" placeholder="First day" value={range.start} onChange={(start) => onChoose({ ...range, start })} />
      <DayInput
        label="To"
        placeholder="Today"
        value={range.end}
        onChange={(end) => onChoose({ ...range, end })}
        error={backwards ? "Before “From”" : undefined}
      />
    </Group>
  );
}

type DayInputProps = { label: string; placeholder: string; value: string | null; onChange: (value: string | null) => void; error?: string };

function DayInput({ label, placeholder, value, onChange, error }: DayInputProps) {
  return (
    <DateInput
      size="xs"
      aria-label={label}
      w={DATE_INPUT_WIDTH}
      placeholder={placeholder}
      valueFormat={DATE_INPUT_FORMAT}
      dateParser={parseDateInput}
      leftSection={<IconCalendar size={ICON_SIZE} />}
      clearable
      value={value}
      onChange={onChange}
      error={error}
    />
  );
}
