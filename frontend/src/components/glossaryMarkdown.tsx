import type { ReactNode } from "react";
import { List, Text } from "@mantine/core";

/**
 * The small slice of markdown the glossary actually uses, rendered.
 *
 * `seestack/data/glossary.md` is prose, and keeping it a readable `.md` file is
 * the point — it is edited as prose, by whoever is explaining the word. That
 * leaves the rendering to be done somewhere, and the two obvious answers are
 * both worse than this one: stripping the markup server-side loses the bullet
 * list that "Master dark / flat / bias" genuinely needs, and pulling in a
 * markdown library adds a dependency (and an HTML sanitiser to go with it) to
 * render four constructs.
 *
 * So: paragraphs, `- ` bullet lists, `**bold**`, `*italic*` and `` `code` ``,
 * and nothing else. Anything it doesn't recognise — including anything that
 * looks like HTML — comes out as literal text, because every span here is a
 * React child rather than markup. There is no `dangerouslySetInnerHTML` in this
 * file and there must never be one: the source is a file we ship, but "we ship
 * it" is not a reason to hand a string to the DOM as markup.
 */

/** `**bold**`, `*italic*` and `` `code` `` inside one line of prose. */
export function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  // One pass, longest marker first so `**` is never read as two `*`.
  const re = /\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] !== undefined) {
      out.push(<b key={key++}>{m[1]}</b>);
    } else if (m[2] !== undefined) {
      out.push(<i key={key++}>{m[2]}</i>);
    } else {
      out.push(<code key={key++}>{m[3]}</code>);
    }
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "ul"; items: string[] };

/** Split a body into paragraphs and bullet lists. Exported for its own test:
 *  the block split is where a stray blank line changes what a reader sees. */
export function parseBlocks(body: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of body.split(/\n\s*\n/)) {
    const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!lines.length) continue;
    if (lines[0].startsWith("- ")) {
      // A wrapped bullet continues the one above it, the way markdown means it.
      const items: string[] = [];
      for (const line of lines) {
        if (line.startsWith("- ")) items.push(line.slice(2));
        else if (items.length) items[items.length - 1] += ` ${line}`;
      }
      blocks.push({ kind: "ul", items });
    } else {
      blocks.push({ kind: "p", lines });
    }
  }
  return blocks;
}

/** A glossary entry's body as React. Hard-wrapped source lines are joined back
 *  into flowing paragraphs — the file is wrapped for editing, not for reading. */
export function GlossaryBody({ body }: { body: string }) {
  return (
    <>
      {parseBlocks(body).map((block, i) =>
        block.kind === "ul" ? (
          <List key={i} size="sm" spacing={4} mt="xs" withPadding>
            {block.items.map((item, j) => (
              <List.Item key={j}>{renderInline(item)}</List.Item>
            ))}
          </List>
        ) : (
          <Text key={i} size="sm" mt={i === 0 ? 0 : "xs"}>
            {renderInline(block.lines.join(" "))}
          </Text>
        ),
      )}
    </>
  );
}
