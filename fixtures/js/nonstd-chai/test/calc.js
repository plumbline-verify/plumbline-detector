const { expect } = require("chai");
const { add } = require("../src/calc");

describe("add", function () {
  it("is truthy", function () {
    expect(add(1, 1)).to.be.ok;
    expect(add(0, 0)).to.equal(0);
  });
});
