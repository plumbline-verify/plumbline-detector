const { add } = require("./calc");

test("bare expect", () => {
  expect(add(1, 1));
});

test("uncalled matcher", () => {
  expect(add(1, 1)).toBeTruthy;
});

test("constant", () => {
  add(1, 1);
  expect(true).toBe(true);
});

test("unawaited", () => {
  expect(Promise.resolve(add(1, 1))).resolves.toBe(2);
});
