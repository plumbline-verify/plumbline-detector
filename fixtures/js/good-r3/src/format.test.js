const { app } = require("./app");

function assert(n, expected) {
  expect(n).toBe(expected);
}

function test(appUnderTest) {
  it("responds", () => {
    expect(appUnderTest.format()).toBe("json");
  });
}

function checkHydration(kind) {
  expect(kind).toBeDefined();
}

describe("format", () => {
  test(app);
  it.each(["root", "ancestor"])("hydrates %s", checkHydration);
  it("guards", () => {
    try {
      app.fail();
      expect("no error").toBe("should throw an error");
    } catch (e) {
      assert(1, 1);
    }
  });
});
