import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GlossaryBody, parseBlocks, renderInline } from "./glossaryMarkdown";

function body(md: string) {
  return render(
    <MantineProvider><GlossaryBody body={md} /></MantineProvider>,
  );
}

describe("parseBlocks", () => {
  it("joins a hard-wrapped paragraph back into one flowing line", () => {
    // The source file is wrapped for editing at ~80 columns; a reader must not
    // see those breaks.
    const blocks = parseBlocks("One sentence that was\nwrapped in the file.");
    expect(blocks).toEqual([
      { kind: "p", lines: ["One sentence that was", "wrapped in the file."] },
    ]);
  });

  it("splits paragraphs on a blank line", () => {
    expect(parseBlocks("First.\n\nSecond.")).toHaveLength(2);
  });

  it("reads a `- ` run as one list", () => {
    const blocks = parseBlocks("- one;\n- two;\n- three.");
    expect(blocks).toEqual([{ kind: "ul", items: ["one;", "two;", "three."] }]);
  });

  it("folds a wrapped bullet into the bullet above it", () => {
    const blocks = parseBlocks("- a **dark** is shot with the lens capped,\n  and records hot pixels;\n- a flat.");
    expect(blocks).toEqual([{
      kind: "ul",
      items: ["a **dark** is shot with the lens capped, and records hot pixels;", "a flat."],
    }]);
  });
});

describe("renderInline", () => {
  it("renders bold, italic and code", () => {
    body("**RGGB** is *the* `pattern`");
    expect(screen.getByText("RGGB").tagName).toBe("B");
    expect(screen.getByText("the").tagName).toBe("I");
    expect(screen.getByText("pattern").tagName).toBe("CODE");
  });

  it("reads `**` as bold rather than as two italics", () => {
    const out = renderInline("**both**");
    expect(out).toHaveLength(1);
  });

  it("leaves anything it doesn't know as literal text", () => {
    // Not markup, and deliberately so: every span is a React child, so there is
    // no path from the glossary file to raw HTML in the DOM.
    body("a <b>tag</b> and a ~~strike~~");
    expect(screen.getByText(/a <b>tag<\/b> and a ~~strike~~/)).toBeTruthy();
    expect(document.querySelector("b")).toBeNull();
  });
});

describe("GlossaryBody", () => {
  it("renders a paragraph and a list from one entry", () => {
    body("Lead line.\n\n- one;\n- two.");
    expect(screen.getByText("Lead line.")).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders nothing at all for an empty body", () => {
    // Asserted on the elements, not on `textContent`: MantineProvider injects a
    // <style> block of its own into the container, so the text of an "empty"
    // render is never literally empty.
    const { container } = body("");
    expect(container.querySelectorAll("p, ul")).toHaveLength(0);
  });
});
