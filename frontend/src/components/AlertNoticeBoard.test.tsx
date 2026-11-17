import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AlertNoticeBoard, type AlertNotice } from "./AlertNoticeBoard";
import { NOTICE_PRIORITY } from "./NoticeBoard";

function board(items: (AlertNotice | null)[], spacing: { mt?: string; mb?: string } = {}) {
  return render(
    <MantineProvider>
      <div data-testid="host">
        <AlertNoticeBoard data-testid="board" items={items} {...spacing} />
      </div>
    </MantineProvider>,
  );
}

// The options the Editor's notes needed when they moved onto the board
// (⭐ declutter slice 4); the folding itself is pinned by StackNoticeBoard.test.
describe("AlertNoticeBoard", () => {
  it("leaves no spacer behind when it has nothing to say", () => {
    board([null], { mb: "xs" });
    expect(screen.getByTestId("host")).toBeEmptyDOMElement();
  });

  it("gives a dismissible note its close button", () => {
    const onClose = vi.fn();
    board([{ key: "auto", priority: NOTICE_PRIORITY.info, color: "violet",
      title: "What Auto-process did", text: "Applied a stretch.", onClose }]);
    fireEvent.click(screen.getByRole("button"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("puts a note's test id and its fix's icon on the note itself", () => {
    board([{ key: "s", priority: NOTICE_PRIORITY.warning, color: "orange", testId: "leveling-stranded",
      text: "No effect", fix: { label: "Move it to the top", onClick: () => {},
        leftSection: <span data-testid="fix-icon" /> } }]);
    expect(screen.getByTestId("leveling-stranded")).toHaveTextContent("No effect");
    expect(screen.getByRole("button", { name: "Move it to the top" }))
      .toContainElement(screen.getByTestId("fix-icon"));
  });
});
