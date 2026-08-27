/** How the grainier-newest note says the size of the gap. Pure. */

/** Past this much, a percentage stops reading as a quantity. */
const MULTIPLE_FROM_PERCENT = 200;

/**
 * The "how much grainier" clause, as `{ amount, joiner }` — rendered as
 * `It has ${amount} ${joiner} your 14 May stack`.
 *
 * `percent_grainier` is honest at any size, but printing it raw stops reading as
 * a quantity once the gap is large: a manual restack of a handful of subs
 * against a 500-sub master gives *"about 2400% more background grain"*, which is
 * arithmetically right and reads as a bug — exactly the wrong impression for a
 * note whose whole job is to make the app look trustworthy at the moment the
 * picture got worse. Past a tripling, say it the way anyone would out loud:
 * *"about 25.0× as much background grain as …"*.
 *
 * Nothing else changes — the endpoint reports the same number, and the ordinary
 * band (where nearly every real firing lands, the bar being ~17.6%) still reads
 * as a percentage.
 */
export function grainierGap(percent: number): { amount: string; joiner: string } {
  if (percent >= MULTIPLE_FROM_PERCENT) {
    const times = 1 + percent / 100;
    return {
      amount: `about ${times.toFixed(1)}× as much background grain`,
      joiner: "as",
    };
  }
  return {
    amount: `about ${percent}% more background grain`,
    joiner: "than",
  };
}
