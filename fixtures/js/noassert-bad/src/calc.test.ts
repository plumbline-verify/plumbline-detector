import { add } from "./calc";

describe("add", () => {
  it("does not crash", () => {
    add(1, 2);
  });

  test("logs", () => {
    console.log(add(2, 2));
  });
});
