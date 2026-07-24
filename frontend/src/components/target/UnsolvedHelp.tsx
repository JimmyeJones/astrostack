import { useState } from "react";
import { ActionIcon, Popover, Stack, Text } from "@mantine/core";
import { IconHelpCircle } from "@tabler/icons-react";

/** A small, always-visible "?" explainer for the "N not located yet" badge.
 *
 * The badge honestly surfaces how many accepted subs never plate-solved (so they
 * silently never reached the stack), but "located" / "plate-solve" is unexplained
 * jargon to a first-light Seestar owner. Seeing an orange "200 not located yet"
 * with no context, a beginner can read it as a scary error — the plain-language
 * breakdown only appears if they happen to *hover* the badge to discover it. This
 * gives the explanation a visible affordance right beside the number: what
 * plate-solving is, that it's usually harmless, and the one thing to try.
 *
 * Pure presentation — no props, no data, no behaviour change. Render it only when
 * there actually are unsolved subs to explain.
 */
export function UnsolvedHelp() {
  const [opened, setOpened] = useState(false);
  return (
    <Popover
      width={300}
      position="bottom"
      withArrow
      shadow="md"
      opened={opened}
      onChange={setOpened}
    >
      <Popover.Target>
        <ActionIcon
          variant="subtle"
          color="gray"
          size="sm"
          radius="xl"
          aria-label="What does 'not located yet' mean?"
          style={{ cursor: "help" }}
          onClick={() => setOpened((o) => !o)}
        >
          <IconHelpCircle size={16} />
        </ActionIcon>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap={6}>
          <Text size="sm" fw={600}>
            What does &ldquo;not located yet&rdquo; mean?
          </Text>
          <Text size="xs" c="dimmed">
            Plate-solving works out exactly where in the sky each sub is pointing, so
            your subs can be lined up and stacked. Subs that can&rsquo;t be located
            are left out — this is common on faint or few-star fields and usually
            harmless: the located subs still stack into your picture.
          </Text>
          <Text size="xs" c="dimmed">
            To locate more, make sure ASTAP&rsquo;s star database is installed (in
            Settings), and remember that longer or more subs solve more easily.
          </Text>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
