// Pure, framework-agnostic helpers pulled out of the page components so
// they're independently unit-testable (see validation.test.ts).

// `website` is sourced from the trusted, admin-run IPEDS import today, but
// a future catalog-adapter-scraped source (docs/PHASE_2_CATALOG_DESIGN.md)
// would be less trustworthy — reject anything that isn't http(s) rather
// than assuming a bare string is always a safe href (e.g. `javascript:`).
export function safeWebsiteHref(website: string): string | null {
  const trimmed = website.trim();
  // If the input already looks like it carries some URI scheme (a leading
  // `word:`), only accept it as-is when that scheme is http/https — never
  // silently reinterpret a non-http(s) scheme (javascript:, data:, file:,
  // ...) as a bare hostname by prepending https://, which would otherwise
  // just mangle it into a different-but-still-wrong URL instead of
  // rejecting it outright.
  const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(trimmed);
  const candidate = hasScheme ? trimmed : `https://${trimmed}`;
  try {
    const url = new URL(candidate);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

// Backend requires exactly 2 chars (api/routes.py: min_length=max_length=2
// on the `state` query param). Drop anything else client-side rather than
// send an invalid param that would 422.
export function normalizeStateFilter(input: string): string | undefined {
  return input.length === 2 ? input : undefined;
}
