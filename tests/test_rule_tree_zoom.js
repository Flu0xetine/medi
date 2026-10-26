/* Exercise zoom sizing against the real rule-tree renderer without a browser dependency. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.children = [];
    this.style = {};
    this.listeners = new Map();
    this.classList = {remove() {}, add() {}, toggle() {}};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
  querySelectorAll() { return []; }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  getBoundingClientRect() { return {left: 10, top: 20}; }
}

const viewport = new Element();
viewport.clientWidth = 900;
viewport.clientHeight = 600;
const stage = new Element();
stage.parentElement = viewport;
const container = new Element();
container.parentElement = stage;
container.scrollWidth = 2400;
container.scrollHeight = 1200;
const context = vm.createContext({
  window: {},
  document: {createElement() { return new Element(); }},
});
const source = fs.readFileSync(path.join(__dirname, '../src/medi/web/static/rule_tree.js'), 'utf8');
vm.runInContext(source, context);
const announced = [];
const tree = context.window.RuleTree.create(container, {label: 'A', result: {grade: 'A', has_r: false}}, value => announced.push(value));

assert.equal(tree.fit(), 0.375, 'fit must use both natural width and height');
assert.equal(stage.style.width, '900px');
assert.equal(stage.style.height, '450px');
assert.equal(container.style.transform, 'scale(0.375)');
assert.equal(tree.setZoom(1.5), 1.5);
assert.equal(stage.style.width, '3600px');
assert.equal(stage.style.height, '1800px');
assert.equal(container.style.transform, 'scale(1.5)');

viewport.scrollLeft = 300;
viewport.scrollTop = 120;
let prevented = false;
viewport.listeners.get('wheel')({
  deltaY: -100, deltaMode: 0, clientX: 160, clientY: 120,
  preventDefault() { prevented = true; },
});
assert.equal(prevented, true, 'wheel zoom must suppress page scrolling');
const wheelZoom = tree.getZoom();
assert.ok(wheelZoom > 1.5);
assert.ok(Math.abs(viewport.scrollLeft - (300 * wheelZoom - 150)) < 0.001);
assert.ok(Math.abs(viewport.scrollTop - ((220 / 1.5) * wheelZoom - 100)) < 0.001);
assert.equal(announced.at(-1), wheelZoom);

prevented = false;
viewport.listeners.get('wheel')({
  deltaY: 100, deltaMode: 0, ctrlKey: true, clientX: 160, clientY: 120,
  preventDefault() { prevented = true; },
});
assert.equal(prevented, true, 'trackpad pinch wheel must suppress browser zoom');
assert.ok(tree.getZoom() < wheelZoom);

let gesturePrevented = false;
viewport.listeners.get('gesturestart')({preventDefault() { gesturePrevented = true; }});
const beforeGesture = tree.getZoom();
viewport.listeners.get('gesturechange')({
  scale: 1.2, clientX: 160, clientY: 120,
  preventDefault() { gesturePrevented = true; },
});
assert.equal(gesturePrevented, true);
assert.ok(Math.abs(tree.getZoom() - beforeGesture * 1.2) < 0.001);

const beforeLargeWheel = tree.getZoom();
viewport.listeners.get('wheel')({
  deltaY: -2000, deltaMode: 0, clientX: 160, clientY: 120,
  preventDefault() {},
});
assert.ok(tree.getZoom() <= beforeLargeWheel * 1.25 + 0.000001,
  'a large wheel delta must not jump many zoom levels in one event');

const beforeTrackpadScroll = tree.getZoom();
let scrollPrevented = false;
viewport.listeners.get('wheel')({
  deltaY: 12, deltaMode: 0, ctrlKey: false, clientX: 160, clientY: 120,
  preventDefault() { scrollPrevented = true; },
});
assert.equal(scrollPrevented, false, 'two-finger scrolling should remain available');
assert.equal(tree.getZoom(), beforeTrackpadScroll);
