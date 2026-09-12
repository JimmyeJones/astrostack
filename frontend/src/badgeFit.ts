/** How a badge in a table survives a phone.
 *
 * A Mantine `Badge` is `overflow: hidden; text-overflow: ellipsis`, so inside a
 * table cell it contributes **no min-content width**: when the table is wider
 * than the screen the column squeezes to nothing and the label is ellipsised
 * *inside the badge*, where scrolling the table can never reach it. That is not
 * a truncated name with the full value elsewhere — it is the value itself,
 * gone.
 *
 * v0.434.1 found and fixed this on the Target page's Nights card (a night's
 * verdict rendering as "SH…"); v0.436.2 found the identical failure on the
 * Tonight planner's score column — **145 clipped badges on one phone-width
 * page**, invisible for as long as it was because no dogfood pass had an
 * observing site, so that table had never been drawn with rows in it. Two
 * independent instances of one mechanism is the point at which the rule belongs
 * in one place rather than in each table that happens to have been measured.
 *
 * `max-content` makes the badge ask for its own text, so the **table** grows
 * and its scroll container scrolls — the honest failure for a table too wide
 * for a phone, and the only one a gesture can undo. It is content-independent:
 * it follows whatever the label says, rather than a width picked against
 * today's words, so a longer verdict or a three-digit score cannot re-break it.
 */
export const NO_SHRINK = { minWidth: "max-content" } as const;

/** …and a short cell value is one line, not three.
 *
 * The same squeeze, other half: at 420 px the Nights card's first column
 * wrapped "16 Nov 2024" over three lines and stood the rows at 70 px against
 * 31 px on a desktop. Use it on cells whose content is a single short token (a
 * date, a clock time, an angle) — never on prose, which should wrap.
 */
export const NO_WRAP = { whiteSpace: "nowrap" } as const;
