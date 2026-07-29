// Decide whether a nav link should render as "active" for the current path.
//
// The old inline logic used a bare `location.pathname.startsWith(l.to)`, which
// treats one route as active whenever another route's path is a *prefix* of it:
// `/sky-so-far` starts with `/sky`, so visiting "Your sky, so far" lit up both
// that link *and* "Sky Map" at once. Match on whole path segments instead — the
// exact path, or the path followed by a "/" (a real sub-route like
// `/library/M31`) — so a shared prefix that isn't a segment boundary no longer
// double-highlights.
export function isNavActive(pathname: string, to: string, end?: boolean): boolean {
  if (end) return pathname === to;
  return pathname === to || pathname.startsWith(to + "/");
}
