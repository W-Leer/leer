import { describe, expect, test } from "bun:test";
import { resolveProjectSlug, withProjectParam } from "./projects";

const projects = [
  { id: "1", name: "recent", slug: "recent" },
  { id: "2", name: "older", slug: "older" },
];

describe("resolveProjectSlug", () => {
  test("uses the first preferred slug that exists", () => {
    expect(resolveProjectSlug(projects, ["older", "recent"])).toBe("older");
  });

  test("skips preferred slugs that no longer exist", () => {
    expect(resolveProjectSlug(projects, ["deleted", null, "older"])).toBe("older");
  });

  test("falls back to the most recently active project", () => {
    expect(resolveProjectSlug(projects, [null, undefined])).toBe("recent");
  });

  test("is null when there are no projects", () => {
    expect(resolveProjectSlug([], ["recent"])).toBeNull();
  });
});

describe("withProjectParam", () => {
  test("adds the project and keeps other params", () => {
    expect(withProjectParam("/?q=agent&status=failed", "older")).toBe("/?q=agent&status=failed&project=older");
  });

  test("replaces an existing project", () => {
    expect(withProjectParam("/?project=recent", "older")).toBe("/?project=older");
  });

  test("removes the project when null", () => {
    expect(withProjectParam("/?project=recent", null)).toBe("/");
  });
});
