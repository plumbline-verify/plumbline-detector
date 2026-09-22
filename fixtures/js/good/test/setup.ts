import { expect } from "vitest";

expect.extend({
  toBeSum(received: number, a: number, b: number) {
    const pass = received === a + b;
    return { pass, message: () => `expected ${received} to be ${a} + ${b}` };
  },
});
