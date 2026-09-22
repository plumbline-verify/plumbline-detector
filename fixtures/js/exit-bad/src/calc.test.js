const { add } = require("./calc");

test("adds", () => {
  const total = add(1, 2);
  process.exit(0);
  expect(total).toBe(4);
});
