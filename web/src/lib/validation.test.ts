import { describe, expect, it } from "vitest";
import { normalizeStateFilter, safeWebsiteHref } from "./validation";

describe("safeWebsiteHref", () => {
  it("adds https:// to a bare domain (typical IPEDS WEBADDR shape)", () => {
    expect(safeWebsiteHref("www.lsu.edu/")).toBe("https://www.lsu.edu/");
  });

  it("keeps an already-https URL as-is", () => {
    expect(safeWebsiteHref("https://www.lsu.edu")).toBe("https://www.lsu.edu/");
  });

  it("accepts plain http", () => {
    expect(safeWebsiteHref("http://example.edu")).toBe("http://example.edu/");
  });

  it("rejects a javascript: URI", () => {
    expect(safeWebsiteHref("javascript:alert(1)")).toBeNull();
  });

  it("rejects a data: URI", () => {
    expect(safeWebsiteHref("data:text/html,<script>alert(1)</script>")).toBeNull();
  });

  it("rejects a file: URI", () => {
    expect(safeWebsiteHref("file:///etc/passwd")).toBeNull();
  });

  it("returns null for an unparseable string", () => {
    expect(safeWebsiteHref("not a url at all ://")).toBeNull();
  });

  it("known limitation: a bare host:port string reads as a non-http scheme and is rejected", () => {
    // "localhost:3000" matches the leading-`word:` scheme heuristic, so
    // it's treated as scheme "localhost" rather than a bare hostname with
    // a port — and gets rejected rather than mangled. Documented rather
    // than fixed: real IPEDS WEBADDR values are always bare domains with
    // no port (verified against real 2023 data), so this doesn't occur in
    // practice; a true host:port frontend URL would need `//` disambiguation
    // if this ever becomes a real input shape.
    expect(safeWebsiteHref("localhost:3000")).toBeNull();
  });
});

describe("normalizeStateFilter", () => {
  it("passes through a valid 2-letter code", () => {
    expect(normalizeStateFilter("LA")).toBe("LA");
  });

  it("drops empty input", () => {
    expect(normalizeStateFilter("")).toBeUndefined();
  });

  it("drops a 1-character partial entry", () => {
    expect(normalizeStateFilter("L")).toBeUndefined();
  });

  it("drops input longer than 2 characters", () => {
    expect(normalizeStateFilter("California")).toBeUndefined();
  });
});
