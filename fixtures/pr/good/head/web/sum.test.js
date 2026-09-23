const { strictEqual } = require('node:assert')
const test = require('node:test')
const { add } = require('../web/add')

test('adds', () => {
  strictEqual(add(1, 2), 3)
})

test('adds negatives', () => {
  strictEqual(add(-1, -2), -3)
})

test('adds zero', () => {
  strictEqual(add(0, 0), 0)
})
