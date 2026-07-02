import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QueryError } from "./QueryError";

function renderError(props: Partial<React.ComponentProps<typeof QueryError>> = {}) {
  return render(
    <MantineProvider>
      <QueryError error={new Error("500: boom")} {...props} />
    </MantineProvider>,
  );
}

describe("QueryError", () => {
  it("shows the error message", () => {
    renderError();
    expect(screen.getByText("500: boom")).toBeInTheDocument();
    expect(screen.getByText("Couldn't load this page")).toBeInTheDocument();
  });

  it("falls back to a generic message for non-Error values", () => {
    renderError({ error: "not an Error instance" });
    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  });

  it("omits the retry button when onRetry isn't passed", () => {
    renderError();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", () => {
    const onRetry = vi.fn();
    renderError({ onRetry });
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
