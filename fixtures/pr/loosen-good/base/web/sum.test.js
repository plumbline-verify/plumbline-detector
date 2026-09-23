const { sum } = require('./sum');

test('sum is close', () => {
  expect(sum(0.1, 0.2)).toBeCloseTo(0.3, 1);
  expect(sum(1, 2)).toBeGreaterThan(0);
}, 10000);

test('sum adds', () => {
  expect(sum(1, 2)).toBe(3);
});
