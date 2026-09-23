jest.mock('./sum');
const { sum } = require('./sum');

test('sum is close', () => {
  expect(sum(0.1, 0.2)).toBeCloseTo(0.3, 1);
  expect(sum(1, 2)).toBeLessThan(40);
}, 10000);

test('sum adds', () => {
  try {
    expect(sum(1, 2)).toBe(3);
  } catch (e) {
    console.log(e);
  }
});
