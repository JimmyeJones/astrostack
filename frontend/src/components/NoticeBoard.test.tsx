import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import { describe, expect, it } from "vitest";
import { NoticeBoard, NOTICE_PRIORITY, type Notice } from "./NoticeBoard";

function board(items: Notice[], inlineCount?: number) {
  return render(
    <MantineProvider>
      <NoticeBoard items={items} inlineCount={inlineCount} />
    </MantineProvider>,
  );
}

const note = (key: string, priority: number, text: string): Notice => ({
  key,
  priority,
  node: <div>{text}</div>,
});

/** A note that says nothing — the shape most of this app's notes take when they
 *  have no news (they fetch their own data and return null). */
const silent = (key: string, priority: number): Notice => ({
  key,
  priority,
  node: null,
});

/** A note that only appears after an async settle, like a note whose query
 *  resolves a tick after mount. The parent does not re-render for this. */
function LateNote({ text }: { text: string }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setReady(true), 0);
    return () => clearTimeout(t);
  }, []);
  return ready ? <div>{text}</div> : null;
}

describe("NoticeBoard", () => {
  it("shows the two most urgent notes inline and folds the rest away", async () => {
    board([
      note("praise", NOTICE_PRIORITY.praise, "Your sharpest yet!"),
      note("blocking", NOTICE_PRIORITY.blocking, "Plate-solving isn't set up"),
      note("warning", NOTICE_PRIORITY.warning, "Very few frames were combined"),
      note("info", NOTICE_PRIORITY.info, "The sky was brighter than usual"),
    ]);

    await waitFor(() => {
      expect(screen.getByText("Plate-solving isn't set up")).toBeVisible();
    });
    expect(screen.getByText("Very few frames were combined")).toBeVisible();
    // Severity, not declaration order, decides: the congratulation waits its turn.
    expect(screen.getByText("Your sharpest yet!")).not.toBeVisible();
    expect(screen.getByText("The sky was brighter than usual")).not.toBeVisible();
    expect(screen.getByRole("button", { name: /2 more notes/ })).toBeInTheDocument();
  });

  it("opens the folded notes in one click, and closes them again", async () => {
    board([
      note("a", NOTICE_PRIORITY.blocking, "Blocking note"),
      note("b", NOTICE_PRIORITY.praise, "Quiet praise"),
    ], 1);

    await waitFor(() => expect(screen.getByText("Quiet praise")).not.toBeVisible());
    fireEvent.click(screen.getByRole("button", { name: /1 more note$/ }));
    expect(screen.getByText("Quiet praise")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /Hide 1 note/ }));
    expect(screen.getByText("Quiet praise")).not.toBeVisible();
  });

  it("counts only the notes that actually have something to say", async () => {
    // Six offered, three silent: the disclosure must promise exactly what it can
    // deliver — a "3 more notes" that opens onto nothing is worse than no line.
    board([
      note("a", NOTICE_PRIORITY.blocking, "First"),
      silent("s1", NOTICE_PRIORITY.warning),
      note("b", NOTICE_PRIORITY.warning, "Second"),
      silent("s2", NOTICE_PRIORITY.advisory),
      note("c", NOTICE_PRIORITY.info, "Third"),
      silent("s3", NOTICE_PRIORITY.praise),
    ]);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /1 more note$/ })).toBeInTheDocument(),
    );
    expect(screen.getByText("Third")).not.toBeVisible();
  });

  it("says nothing at all when no note speaks up", async () => {
    board([silent("s1", NOTICE_PRIORITY.warning), silent("s2", NOTICE_PRIORITY.praise)]);
    await waitFor(() => expect(screen.queryByRole("button")).toBeNull());
  });

  it("picks up a note that only arrives after its data does", async () => {
    // The parent does not re-render when a child's own query resolves, so the
    // count has to come from watching the DOM, not from the render pass.
    board([
      note("a", NOTICE_PRIORITY.blocking, "First"),
      note("b", NOTICE_PRIORITY.warning, "Second"),
      { key: "late", priority: NOTICE_PRIORITY.info, node: <LateNote text="Late arrival" /> },
    ]);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /1 more note$/ })).toBeInTheDocument(),
    );
    expect(screen.getByText("Late arrival")).not.toBeVisible();
  });

  it("shows everything inline when there is nothing to fold", async () => {
    board([
      note("a", NOTICE_PRIORITY.blocking, "First"),
      note("b", NOTICE_PRIORITY.warning, "Second"),
    ]);
    await waitFor(() => expect(screen.getByText("First")).toBeVisible());
    expect(screen.getByText("Second")).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
