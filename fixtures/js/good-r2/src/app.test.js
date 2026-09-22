const request = require("supertest");
const assert = require("assert");
const { app } = require("./app");

function baseCheck(expected, value) {
  expect(value).toBe(expected);
}
const checkTrue = baseCheck.bind(null, true);

function testToggle(value) {
  expect(value).toBeDefined();
}
function runWithFixture(tester) {
  tester(1);
}

describe("app", () => {
  it("responds", (done) => {
    request(app).get("/").expect(200, done);
  });

  it("bound helper", () => {
    checkTrue(true);
  });

  it("runner with asserting callback", () => {
    runWithFixture(testToggle);
  });

  it("warns", () => {
    expect("deprecated option").toHaveBeenWarned();
  });

  it("never reaches", () => {
    try {
      app.fail();
      assert(0);
    } catch (e) {
      expect(e).toBeDefined();
    }
  });
});
