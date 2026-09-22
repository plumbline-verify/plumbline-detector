const { add } = require("./calc");

describe("add", () => {
  it("adds", () => {
    expect(add(2, 3)).toBe(5);
  });

  it.skip("negative", () => {
    expect(add(-1, -1)).toBe(-2);
  });

  xit("zero", () => {
    expect(add(0, 0)).toBe(0);
  });

  it.todo("large numbers");

  it("pending without body");
});

xdescribe("disabled suite", () => {
  it("never", () => {
    expect(add(1, 1)).toBe(2);
  });
});
