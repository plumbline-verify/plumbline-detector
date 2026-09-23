jest.mock('./db');
const { sum } = require('./sum');

test('sum is close', () => {
  expect(sum(0.1, 0.2)).toBeCloseTo(0.3, 5);
  expect(sum(1, 2)).toBeGreaterThan(2);
}, 1000);

test('sum adds', () => {
  try {
    expect(sum(1, 2)).toBe(3);
  } catch (e) {
    expect(e).toBeUndefined();
  }
});
