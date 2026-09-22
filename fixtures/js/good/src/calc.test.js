import { add } from "./calc";
import { render, screen } from "@testing-library/react";

function expectSum(a, b, total) {
  expect(add(a, b)).toBe(total);
}

describe("add", () => {
  it("adds", () => {
    expect(add(2, 3)).toBe(5);
  });

  test("via helper", () => {
    expectSum(1, 1, 2);
  });

  it("resolves", async () => {
    await expect(Promise.resolve(add(1, 2))).resolves.toBe(3);
  });

  it("returns the promise", () => {
    return expect(Promise.resolve(4)).resolves.toBe(4);
  });

  it("renders", () => {
    render(null);
    screen.getByText("hello");
  });

  test.each([[1, 1, 2]])("table %i + %i", (a, b, expected) => {
    expect(add(a, b)).toBe(expected);
  });
});
