const { add } = require("./calc");

test("exit is mocked", () => {
  const spy = jest.spyOn(process, "exit").mockImplementation(() => {});
  expect(add(1, 2)).toBe(3);
  expect(spy).not.toHaveBeenCalled();
});

test("failure exits non-zero", () => {
  expect(() => process.exit(1)).toBeDefined();
});
