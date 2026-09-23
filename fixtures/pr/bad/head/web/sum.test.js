const { strictEqual } = require('node:assert')
const test = require('node:test')
const { add } = require('../web/add')

test('adds', () => {
  strictEqual(add(1, 2), 3)
})

test.skip('adds negatives', () => {
  strictEqual(add(-1, -2), -3)
})
