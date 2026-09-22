const { add } = require("./calc");

it.only("focused", () => {
  expect(add(1, 1)).toBe(2);
});

it("excluded one", () => {
  expect(add(2, 2)).toBe(4);
});

it("excluded two", () => {
  expect(add(3, 3)).toBe(6);
});
