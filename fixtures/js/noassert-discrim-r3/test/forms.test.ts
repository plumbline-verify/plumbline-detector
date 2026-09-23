import { test, it, expect } from "vitest";
import assert from "node:assert";
import tspl from "@matteo.collina/tspl";
import { check } from "./helper.js";
import { util } from "../src/util";

function withRoot(fn) {
  return async () => {
    await fn();
  };
}

it("call-produced body", withRoot(async () => {
  expect(1 + 1).toBe(2);
}));

test("assertion method passed as argument", () => {
  check(assert.equal, { level: 30 }, 30);
});

test("tspl plan", async (t) => {
  const plan = tspl(t, { plan: 1 });
  plan.equal(1, 1);
  await plan;
});

test("node:test t.assert", (t) => {
  t.assert.ifError(null);
});

test("type-level assertEqual", () => {
  type A = string;
  util.assertEqual<A, string>(true);
});

test("ts-expect-error under typecheck", () => {
  const n: number = 1;
  // @ts-expect-error assigning a number to a string must not compile
  const s: string = n;
});

test("satisfies under typecheck", () => {
  const v = { a: 1 } satisfies { a: number };
});

test("awaited through Promise.all", async () => {
  await Promise.all([expect(Promise.reject(new Error("x"))).rejects.toThrow("x")]);
});

test("real gap", () => {
  const x = 1 + 1;
});
