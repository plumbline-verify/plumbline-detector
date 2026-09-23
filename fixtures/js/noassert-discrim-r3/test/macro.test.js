import test from "ava";

const same = test.macro(async (t, input, expected) => {
  t.is(input, expected);
});

test("macro with args", same, 1, 1);
