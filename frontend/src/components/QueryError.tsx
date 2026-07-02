import { Alert, Button, Center, Stack, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";

/** A fetch failed — tell the user instead of spinning a loader forever. */
export function QueryError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <Center h={300}>
      <Stack align="center" gap="sm" maw={460}>
        <Alert color="red" title="Couldn't load this page" icon={<IconAlertTriangle size={18} />} w="100%">
          <Text size="sm">{message}</Text>
        </Alert>
        {onRetry ? (
          <Button variant="light" size="xs" onClick={onRetry}>Retry</Button>
        ) : null}
      </Stack>
    </Center>
  );
}
