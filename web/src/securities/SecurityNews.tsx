import { Alert, Anchor, Skeleton, Stack, Text, Title } from "@mantine/core";

import { formatDateTime } from "../ui/format";
import { CHART_HEIGHT } from "../ui/theme";
import { useNews } from "./useSecurity";

/** The latest articles about the security, newest first, each linking to where it was published. */
export function SecurityNews({ symbol }: { symbol: string }) {
  const state = useNews(symbol);
  return (
    <div>
      <Title order={2} mb="sm">
        News
      </Title>
      {state.status === "loading" && <Skeleton h={CHART_HEIGHT / 2} />}
      {state.status === "error" && (
        <Alert color="yellow" title="News unavailable">
          {state.message}
        </Alert>
      )}
      {state.status === "loaded" &&
        (state.articles.length === 0 ? (
          <Text c="dimmed">No recent news about {symbol}.</Text>
        ) : (
          <Stack gap="md">
            {state.articles.map((article) => (
              <div key={article.url}>
                {/* Opens the publisher's page in a new tab, leaving the app as it is. */}
                <Anchor href={article.url} target="_blank" rel="noopener noreferrer" fw={500}>
                  {article.headline}
                </Anchor>
                <Text c="dimmed" size="xs">
                  {article.source} · {formatDateTime(article.published_at)}
                </Text>
                {article.summary && (
                  <Text size="sm" lineClamp={2}>
                    {article.summary}
                  </Text>
                )}
              </div>
            ))}
            <Text c="dimmed" size="sm">
              From Benzinga, through Alpaca.
            </Text>
          </Stack>
        ))}
    </div>
  );
}
