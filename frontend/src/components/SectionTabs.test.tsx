import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SectionTabs, type PageSection } from "./SectionTabs";

const SECTIONS: PageSection[] = [
  { key: "one", label: "First", node: <p>first section body</p> },
  { key: "two", label: "Second", node: <p>second section body</p> },
  { key: "three", label: "Third", node: <p>third section body</p> },
];

// Prints the current URL so a tab click can be asserted as navigation, which is
// the whole point of this strip over an ordinary tab component.
function Address() {
  const loc = useLocation();
  return <div data-testid="address">{loc.pathname}</div>;
}

// The real page reads the section from the route; mirror that here so the tests
// exercise the same wiring rather than a prop the app never sets by hand.
function Harness() {
  const path = useLocation().pathname;
  const section = path.startsWith("/demo/") ? path.slice("/demo/".length) : undefined;
  return <SectionTabs basePath="/demo" sections={SECTIONS} active={section} />;
}

function renderRouted(path: string) {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={[path]}>
        <Address />
        <Harness />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("SectionTabs", () => {
  it("shows one section at a time and keeps the rest mounted", () => {
    renderRouted("/demo/two");

    expect(screen.getByText("second section body")).toBeVisible();
    // Still in the DOM — the sections share one edit buffer, so switching away
    // must not throw a half-typed value away or refetch anything.
    expect(screen.getByText("first section body")).toBeInTheDocument();
    expect(screen.getByText("first section body")).not.toBeVisible();
    expect(screen.getByText("third section body")).not.toBeVisible();
  });

  it("gives every section a tab", () => {
    renderRouted("/demo/one");
    for (const label of ["First", "Second", "Third"]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
  });

  it("clicking a tab navigates to that section's own URL", () => {
    renderRouted("/demo/one");

    fireEvent.click(screen.getByRole("tab", { name: "Third" }));

    expect(screen.getByTestId("address")).toHaveTextContent("/demo/three");
    expect(screen.getByText("third section body")).toBeVisible();
  });

  it("lands on the first section when the URL names none", () => {
    renderRouted("/demo");
    expect(screen.getByText("first section body")).toBeVisible();
  });

  it("falls back to the first section for an unknown one, rather than showing nothing", () => {
    // An old bookmark to a renamed section must still land somewhere useful.
    renderRouted("/demo/renamed-away");
    expect(screen.getByText("first section body")).toBeVisible();
  });
});
