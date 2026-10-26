/* Run the real doctor's page script with a delayed tree response. No DOM package needed. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.children = [];
    this.listeners = new Map();
    this.value = '';
    this.disabled = false;
    this.classList = {toggle() {}, add() {}, remove() {}};
  }
  setAttribute() {}
  replaceChildren(...children) { this.children = children; this.value = ''; }
  append(...children) { this.children.push(...children); }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
}

async function main() {
  const html = fs.readFileSync(path.join(__dirname, '../src/medi/web/static/doctor.html'), 'utf8');
  const script = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const elements = new Map();
  const documentListeners = new Map();
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
    createElement() { return new Element(); },
    querySelector() { return {scrollIntoView() {}}; },
    addEventListener(name, handler) { documentListeners.set(name, handler); },
    async exitFullscreen() {
      this.fullscreenElement = null;
      documentListeners.get('fullscreenchange')();
    },
  };
  let releaseTree;
  const delayedTree = new Promise(resolve => { releaseTree = resolve; });
  const calls = [];
  let traceCalls = 0;
  const view = {
    setPaths(paths) { calls.push(['paths', paths.length]); },
    setFilter(grade, hasR, index) { calls.push(['filter', grade, hasR, index]); },
    fit() { calls.push(['fit']); return 0.4; },
    getZoom() { return 0.4; },
    setZoom(scale) { calls.push(['zoom', scale]); return scale; },
    clearHighlights() {},
  };
  const context = vm.createContext({
    document,
    window: {RuleTree: {create() { return view; }}},
    fetch(url, options) {
      if (url === '/api/decision-tree') return delayedTree;
      assert.equal(url, '/api/decision-trace');
      assert.equal(options.method, 'POST');
      traceCalls++;
      return Promise.resolve({ok: true, json: async () => ({results: [{grade: 'B2', has_r: false}], paths: []})});
    },
    clearTimeout,
    setTimeout,
    console,
  });
  vm.runInContext(script, context);

  const paths = [
    {grade: 'D2', has_r: false, certainty: 'possible', steps: []},
    {grade: 'D2', has_r: false, certainty: 'possible', steps: []},
  ];
  context.renderResults([{grade: 'D2', has_r: false}], paths);
  elements.get('tree-result-filter').value = 'D2|false';
  context.updatePathChoices();
  elements.get('tree-path-filter').value = '1';
  context.applyTreeFilter();
  releaseTree({ok: true, json: async () => ({tree: {id: 'a'}})});
  await delayedTree;
  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(calls, [
    ['paths', 2],
    ['filter', 'D2', false, 1],
    ['fit'],
  ], 'A delayed tree must restore the already selected result and route');

  const panel = elements.get('rule-tree-panel');
  panel.requestFullscreen = async () => {
    document.fullscreenElement = panel;
    documentListeners.get('fullscreenchange')();
  };
  await elements.get('tree-fullscreen').listeners.get('click')();
  assert.equal(document.fullscreenElement, panel);
  assert.equal(elements.get('tree-fullscreen').textContent, '退出全屏');
  await elements.get('tree-fullscreen').listeners.get('click')();
  assert.equal(document.fullscreenElement, null);
  assert.equal(elements.get('tree-fullscreen').textContent, '全屏查看');
  assert.deepEqual(calls.slice(3), [['fit'], ['zoom', 0.4]], 'Fullscreen must fit and restore zoom');

  vm.runInContext("config={groups:[{name:'基本信息',fields:[{name:'male_sex',label:'男性',type:'boolean'}]}]}; facts={male_sex:{value:true,mentioned:true,evidence:'男性'}}; renderFacts();", context);
  const factGroup = elements.get('fact-editor').children[0];
  const fieldControls = factGroup.children[1].children[1];
  const valueControl = fieldControls.children[0];
  valueControl.value = 'false';
  valueControl.listeners.get('change')();
  assert.equal(traceCalls, 0, 'Editing facts must not regrade before the user clicks the button');
  assert.equal(elements.get('regrade-button').disabled, false);
  assert.match(elements.get('grade-display').children[0].textContent, /待重新定级|点击/);

  await elements.get('regrade-button').listeners.get('click')();
  assert.equal(traceCalls, 1, 'Clicking the button must regrade exactly once');
  assert.equal(elements.get('regrade-button').disabled, true);
  assert.equal(elements.get('grade-display').children[0].textContent, 'B2');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
