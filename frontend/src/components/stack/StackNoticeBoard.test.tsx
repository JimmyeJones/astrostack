import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NOTICE_PRIORITY } from "../NoticeBoard";
import { JUST_DONE_PRIORITY, StackNoticeBoard, type StackNotice } from "./StackNoticeBoard";

function board(items: (StackNotice | null)[]) {
  return render(
    <MantineProvider>
      <StackNoticeBoard data-testid="board" items={items} />
    </MantineProvider>,
  );
}

describe("StackNoticeBoard", () => {
  it("renders nothing at all when no note has anything to say", () => {
    board([null, null]);
    expect(screen.queryByTestId("board")).toBeNull();
  });

  it("keeps a red 'this will fail' and a warning inline, folding the nudges", async () => {
    // The shape that used to be a wall: a streaky night with an imperfect dark
    // put five boxes above "Start stacking".
    board([
      { key: "drizzle", priority: NOTICE_PRIORITY.advisory, color: "blue", text: "Try Drizzle" },
      { key: "weight", priority: NOTICE_PRIORITY.advisory, color: "blue", text: "Weight by quality" },
      { key: "temp", priority: NOTICE_PRIORITY.warning, color: "yellow", text: "Dark is 10 °C off" },
      { key: "size", priority: NOTICE_PRIORITY.blocking, color: "red", text: "Dark is the wrong size" },
      { key: "auto", priority: NOTICE_PRIORITY.info, color: "blue", text: "Auto picks the method" },
    ]);
    await waitFor(() => expect(screen.getByText("Try Drizzle")).not.toBeVisible());
    expect(screen.getByText("Dark is the wrong size")).toBeVisible();
    expect(screen.getByText("Dark is 10 °C off")).toBeVisible();
    expect(screen.getByText("Weight by quality")).not.toBeVisible();
    expect(screen.getByText("Auto picks the method")).not.toBeVisible();

    // Nothing is removed: one click and every note, with its fix, is back.
    fireEvent.click(screen.getByRole("button", { name: /3 more notes/ }));
    expect(screen.getByText("Try Drizzle")).toBeVisible();
    expect(screen.getByText("Auto picks the method")).toBeVisible();
  });

  it("never folds away the Undo of a click just made", async () => {
    board([
      { key: "a", priority: NOTICE_PRIORITY.blocking, color: "red", text: "Wrong-size flat" },
      { key: "b", priority: NOTICE_PRIORITY.blocking, color: "red", text: "Wrong-size dark" },
      { key: "undo", priority: JUST_DONE_PRIORITY, color: "teal", text: "Dropped 4 outlier frames" },
    ]);
    await waitFor(() => expect(screen.getByText("Wrong-size dark")).not.toBeVisible());
    expect(screen.getByText("Dropped 4 outlier frames")).toBeVisible();
    expect(screen.getByText("Wrong-size flat")).toBeVisible();
  });

  it("wires each note's one fix button to its setting change", async () => {
    const onClick = vi.fn();
    board([
      { key: "clip", priority: NOTICE_PRIORITY.warning, color: "yellow", text: "Sigma clip fights min/max",
        fix: { label: "Turn off sigma clipping", onClick, color: "yellow" } },
      { key: "none", priority: NOTICE_PRIORITY.info, color: "blue", text: "No fix here", fix: null },
    ]);
    fireEvent.click(await screen.findByRole("button", { name: "Turn off sigma clipping" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
});
