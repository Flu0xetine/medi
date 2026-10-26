/* Verify that the real renderer stacks only a split with two substantial subtrees. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.children = [];
    this.style = {};
    this.classList = {remove() {}, add() {}, toggle() {}};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
  querySelectorAll() { return []; }
  addEventListener() {}
}

const leaf = name => ({label: name, result: {grade: name, has_r: false}});
const decision = (id, children) => ({
  id, label: id,
  branches: children.map((child, index) => ({outcome: String(index), label: String(index), child})),
});
const wideChild = id => decision(id, [leaf('A'), leaf('B'), leaf('C'), leaf('D'), leaf('E')]);

function render(model) {
  const viewport = new Element();
  viewport.clientWidth = 1200;
  viewport.clientHeight = 700;
  const stage = new Element();
  stage.parentElement = viewport;
  const container = new Element();
  container.parentElement = stage;
  container.scrollWidth = 2000;
  container.scrollHeight = 1000;
  const context = vm.createContext({window: {}, document: {createElement() { return new Element(); }}});
  const source = fs.readFileSync(path.join(__dirname, '../src/medi/web/static/rule_tree.js'), 'utf8');
  vm.runInContext(source, context);
  context.window.RuleTree.create(container, model);
  return container.children[0].children[1];
}

const largeSplit = render(decision('large', [wideChild('left'), wideChild('right')]));
assert.match(largeSplit.className, /tree-branches-stacked/,
  'two large sibling subtrees should stack instead of widening the whole diagram');

const unevenSplit = render(decision('uneven', [leaf('A'), wideChild('right')]));
assert.doesNotMatch(unevenSplit.className, /tree-branches-stacked/,
  'a short branch should stay beside the large subtree rather than lengthening the diagram');

const smallSplit = render(decision('small', [leaf('A'), leaf('B')]));
assert.doesNotMatch(smallSplit.className, /tree-branches-stacked/,
  'terminal pairs should stay horizontal');
