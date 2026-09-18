import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { GlossaryLink } from "./GlossaryLink";
import { HintLabel, StackOptionControl } from "./StackOptionControl";
import type { StackOptionField } from "../api/client";

function renderIn(node: React.ReactNode) {
  return render(
    <MantineProvider>
      <MemoryRouter>{node}</MemoryRouter>
    </MantineProvider>,
  );
}

function field(over: Partial<StackOptionField> = {}): StackOptionField {
  return {
    key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
    default: true, min: null, max: null, step: null, options: null,
    help: "Reject per-pixel outliers.", depends_on: null,
    ...over,
  } as StackOptionField;
}

describe("GlossaryLink", () => {
  it("lands on that term's own anchor, not the top of the page", () => {
    renderIn(<GlossaryLink slug="sigma-clipping" term="Sigma clipping" />);
    const link = screen.getByTestId("glossary-link-sigma-clipping");
    expect(link).toHaveAttribute("href", "/glossary#sigma-clipping");
  });

  it("names the word rather than repeating the control's own label", () => {
    // The label is how a screen reader (and a test) finds the *control*, so an
    // accessible name equal to it would give the row two things with one name.
    renderIn(<GlossaryLink slug="drizzle" term="Drizzle (super-resolution)" />);
    expect(screen.getByLabelText("What is drizzle (super-resolution)?"))
      .toBeInTheDocument();
  });
});

describe("HintLabel", () => {
  it("offers the glossary beside the hint when the descriptor carries a slug", () => {
    renderIn(<HintLabel label="Sigma clipping" hint="Reject outliers."
      glossary="sigma-clipping" />);
    // Both affordances, answering the two different questions.
    expect(screen.getByLabelText("What does this do?")).toBeInTheDocument();
    expect(screen.getByTestId("glossary-link-sigma-clipping")).toBeInTheDocument();
  });

  it("renders exactly as before when there is no slug", () => {
    const { container } = renderIn(<HintLabel label="Output name" hint="A name." />);
    expect(container.querySelector("a")).toBeNull();
  });
});

describe("StackOptionControl", () => {
  it("threads the descriptor's slug through to the label", () => {
    renderIn(<StackOptionControl field={field({ glossary: "sigma-clipping" })}
      value={true} onChange={() => {}} />);
    expect(screen.getByTestId("glossary-link-sigma-clipping"))
      .toHaveAttribute("href", "/glossary#sigma-clipping");
  });

  it("is unchanged for a field an older backend served without one", () => {
    const { container } = renderIn(
      <StackOptionControl field={field()} value={true} onChange={() => {}} />);
    expect(container.querySelector("a")).toBeNull();
  });
});
