import { describe, expect, it } from "vitest";
import { matchesQuery } from "./search";

describe("matchesQuery", () => {
  const name = "tapete pebbletop 4x6 colector de leche";

  it("finds plurals of both kinds", () => {
    expect(matchesQuery(name, "tapetes")).toBe(true);
    expect(matchesQuery(name, "colectores")).toBe(true);
  });

  it("takes the words in any order, and needs all of them", () => {
    expect(matchesQuery(name, "pebbletop tapete")).toBe(true);
    expect(matchesQuery(name, "tapete manguera")).toBe(false);
  });

  it("matches parts of a code", () => {
    expect(matchesQuery("pezonera 7021-2725-190", "2725")).toBe(true);
  });
});
