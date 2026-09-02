import { useState } from "react";
import { ActionIcon, Popover, Stack, Text } from "@mantine/core";
import { IconHelpCircle } from "@tabler/icons-react";

import type { SolveSetup } from "./solveSetup";

/** A small, always-visible "?" explainer for the "N not located yet" badge.
 *
 * The badge honestly surfaces how many accepted subs never plate-solved (so they
 * silently never reached the stack), but "located" / "plate-solve" is unexplained
 * jargon to a first-light Seestar owner. Seeing an orange "200 not located yet"
 * with no context, a beginner can read it as a scary error — the plain-language
 * breakdown only appears if they happen to *hover* the badge to discover it. This
 * gives the explanation a visible affordance right beside the number: what
 * plate-solving is, why these subs were left out, and the one thing to try.
 *
 * The `setup` prop is what stops it contradicting the screen it sits on. When
 * ASTAP or its star database is missing, the Target page shows a **blocking**
 * banner saying the problem "blocks the whole target" — while this popover, a
 * few pixels away, used to call the very same subs "usually harmless: the
 * located subs still stack into your picture". Both sentences were on screen at
 * once, and the reassuring one is the wrong answer in that state: with no
 * solver there are *no* located subs, so nothing stacks at all. Pass the same
 * `SolveSetup` the banner was built from and the explainer says so instead —
 * still reassuringly (no data is lost, one fix brings them all in), just not
 * falsely.
 *
 * Pure presentation — no data fetching, no behaviour change. Render it only when
 * there actually are unsolved subs to explain.
 */
export function UnsolvedHelp({ setup }: { setup?: SolveSetup | null } = {}) {
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
            are left out.
          </Text>
          {setup ? (
            <>
              <Text size="xs" c="dimmed">
                {setup.kind === "astap"
                  ? "Right now none of them can be located, because ASTAP — the "
                    + "program that does the locating — isn't installed yet. That's "
                    + "the orange note above, and until it's sorted no sub can reach "
                    + "your picture."
                  : "Right now none of them can be located, because ASTAP has no star "
                    + "database to match your subs against. That's the orange note "
                    + "above, and until it's sorted no sub can reach your picture."}
              </Text>
              <Text size="xs" c="dimmed">
                Nothing has been lost — your subs are all still here. Fix that one
                thing, re-run solving, and they can join your picture.
              </Text>
            </>
          ) : (
            <>
              <Text size="xs" c="dimmed">
                This is common on faint or few-star fields and usually harmless: the
                located subs still stack into your picture.
              </Text>
              <Text size="xs" c="dimmed">
                To locate more, make sure ASTAP&rsquo;s star database is installed (in
                Settings), and remember that longer or more subs solve more easily.
              </Text>
            </>
          )}
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
