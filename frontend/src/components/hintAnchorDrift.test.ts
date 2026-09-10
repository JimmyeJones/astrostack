/**
 * The drift guard for `HintAnchor`: no plain `<Tooltip>` may be wrapped around a
 * `<Badge>` anywhere in the app.
 *
 * **Why a guard and not another sweep.** The "a Tooltip is invisible on the
 * device the owner actually reads this app on" entry has now been swept six
 * times, and each sweep fixed the sites that existed on the day. Nothing stopped
 * the next one being written the old way — which is exactly how a `<Tooltip>`
 * around a `Badge` survived the first four: the entry lists its open work by
 * *route*, and the badges live in shared components that no route owns.
 *
 * A `Badge` is not a control. Mantine's `Tooltip` ships
 * `events={{ hover: true, focus: false, touch: false }}`, so a plain one around a
 * badge opens on `mouseenter` and on nothing else — on a phone there is no
 * gesture that reaches the words, and unlike a switch there is not even a wrong
 * one to try. That makes "first child is a `Badge`" a mechanically checkable
 * shape, which is what a guard needs.
 *
 * The app's own sources are read through Vite's `import.meta.glob` rather than
 * `node:fs`: no `@types/node` is installed, and this way the guard reads exactly
 * the files the bundler compiles.
 */

import { describe, expect, it } from "vitest";

/** `<Tooltip …>` whose first child element is a `<Badge`, as "file:line". */
export function tooltipsWrappingABadge(
  sources: { name: string; text: string }[],
): string[] {
  const hits: string[] = [];
  for (const { name, text } of sources) {
    const lines = text.split("\n");
    lines.forEach((line, i) => {
      const at = line.indexOf("<Tooltip");
      if (at < 0) return;
      // Only the *first* element under the opening tag decides: that is the
      // anchor Mantine clones, and the one a tap would land on.
      for (let j = i; j < Math.min(i + 14, lines.length); j++) {
        const rest = j === i ? lines[j].slice(at + "<Tooltip".length) : lines[j];
        const m = /<([A-Za-z][A-Za-z0-9.]*)/.exec(rest);
        if (!m) continue;
        if (m[1] === "Badge") hits.push(`${name}:${i + 1}`);
        return;
      }
    });
  }
  return hits;
}

function frontendSources(): { name: string; text: string }[] {
  const raw = import.meta.glob("../**/*.tsx", {
    query: "?raw", import: "default", eager: true,
  }) as Record<string, string>;
  return Object.entries(raw)
    .filter(([name]) => !name.endsWith(".test.tsx"))
    .map(([name, text]) => ({ name: name.replace(/^\.\.\//, ""), text }));
}

describe("no plain Tooltip may be wrapped around a Badge", () => {
  it("finds none in the app — they are all HintAnchor", () => {
    const sources = frontendSources();
    // An empty result is what a clean tree and a mis-scanned one both look like,
    // so pin that the sweep really walked the app before believing it.
    expect(sources.length).toBeGreaterThan(80);
    expect(sources.some((s) => s.name.endsWith("HazyNightBadge.tsx"))).toBe(true);
    expect(sources.some((s) => s.name.endsWith("routes/Tonight.tsx"))).toBe(true);

    expect(tooltipsWrappingABadge(sources)).toEqual([]);
  });

  it("and the guard is armed — it flags one written the old way, with its line", () => {
    expect(tooltipsWrappingABadge([{
      name: "routes/Made Up.tsx",
      text: [
        "export function X() {",
        "  return (",
        "    <Tooltip label={why} multiline w={240} withArrow>",
        '      <Badge size="xs">seams flat</Badge>',
        "    </Tooltip>",
        "  );",
        "}",
      ].join("\n"),
    }])).toEqual(["routes/Made Up.tsx:3"]);
  });

  it("does not flag a Tooltip around something a tap can already reach", () => {
    // The interactive half of the class is a judgement call per site (a button
    // that only previews something is a safe way to find out), so it is not the
    // guard's business.
    expect(tooltipsWrappingABadge([{
      name: "routes/Made Up.tsx",
      text: [
        "    <Tooltip label={why}>",
        '      <ActionIcon aria-label="Delete"><IconTrash /></ActionIcon>',
        "    </Tooltip>",
      ].join("\n"),
    }])).toEqual([]);
  });
});
