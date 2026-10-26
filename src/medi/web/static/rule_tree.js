/* Render the backend's rule tree and reachable paths; never recompute clinical rules here. */
(function () {
  'use strict';

  function makeElement(tag, className, label) {
    const element = document.createElement(tag);
    element.className = className;
    if (label !== undefined) element.textContent = label;
    return element;
  }

  function leafCount(model) {
    if (model.result) return 1;
    return model.branches.reduce((count, branch) => count + leafCount(branch.child), 0);
  }

  function stackLargeSiblingSubtrees(model) {
    // Full pseudocode: count terminal outcomes below each branch; if a binary
    // decision leads to two substantial subtrees, stack them to avoid adding
    // both widths; keep short and terminal branches side by side to limit height.
    return model.branches.length === 2 &&
      model.branches.every(branch => leafCount(branch.child) >= 5);
  }

  function buildNode(model) {
    if (model.result) {
      const card = makeElement('div', 'tree-node tree-leaf', model.label);
      card.setAttribute('aria-label', `${model.result.grade}，R 为${model.result.has_r ? '是' : '否'}`);
      return {element: card, card, branches: new Map()};
    }

    const subtree = makeElement('div', 'tree-subtree');
    const card = makeElement('div', 'tree-node tree-decision', model.label);
    const branchClass = stackLargeSiblingSubtrees(model)
      ? 'tree-branches tree-branches-stacked' : 'tree-branches';
    const branchesElement = makeElement('div', branchClass);
    const branches = new Map();
    subtree.append(card, branchesElement);
    for (const branch of model.branches) {
      const edge = makeElement('div', 'tree-branch');
      const label = makeElement('span', 'tree-edge-label', branch.label);
      const child = buildNode(branch.child);
      edge.append(label, child.element);
      branchesElement.append(edge);
      branches.set(branch.outcome, {edge, child, model: branch.child});
    }
    return {element: subtree, card, branches};
  }

  function create(container, tree, onZoomChange) {
    const root = buildNode(tree);
    container.replaceChildren(root.element);
    const stage = container.parentElement;
    const viewport = stage.parentElement;
    const naturalWidth = Math.max(container.scrollWidth, 1);
    const naturalHeight = Math.max(container.scrollHeight, 1);
    let zoom = 1;

    function setZoom(requested) {
      // Full pseudocode: clamp the scale, transform the tree from its top-left
      // corner, resize its layout stage to the visual bounds, keep overflow scrollable.
      zoom = Math.min(2.5, Math.max(0.05, requested));
      container.style.transform = `scale(${zoom})`;
      stage.style.width = `${naturalWidth * zoom}px`;
      stage.style.height = `${naturalHeight * zoom}px`;
      if (typeof onZoomChange === 'function') onZoomChange(zoom);
      return zoom;
    }

    function zoomAt(requested, clientX, clientY) {
      // Full pseudocode: convert the pointer position into unscaled tree
      // coordinates, change scale, then scroll so that point stays under it.
      const bounds = viewport.getBoundingClientRect();
      const pointerX = clientX - bounds.left;
      const pointerY = clientY - bounds.top;
      const treeX = (viewport.scrollLeft + pointerX) / zoom;
      const treeY = (viewport.scrollTop + pointerY) / zoom;
      const applied = setZoom(requested);
      viewport.scrollLeft = treeX * applied - pointerX;
      viewport.scrollTop = treeY * applied - pointerY;
      return applied;
    }

    function fit() {
      // Fit both dimensions; reset scrolling to reveal the complete diagram.
      const scale = Math.min(1, viewport.clientWidth / naturalWidth,
        viewport.clientHeight / naturalHeight);
      const applied = setZoom(scale);
      viewport.scrollLeft = 0;
      viewport.scrollTop = 0;
      return applied;
    }
    viewport.addEventListener('wheel', event => {
      // Chromium reports trackpad pinch as Ctrl+wheel; Safari emits gesture
      // events below. Small pixel deltas without Ctrl are ordinary two-finger
      // scrolling, so leave them to the scrollable viewport.
      if (!event.deltaY || event.shiftKey ||
          (!event.ctrlKey && event.deltaMode === 0 && Math.abs(event.deltaY) < 40)) return;
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1;
      const factor = Math.min(1.25, Math.max(0.8, Math.exp(-event.deltaY * unit * 0.0015)));
      zoomAt(zoom * factor, event.clientX, event.clientY);
    }, {passive: false});
    let gestureStartZoom = zoom;
    viewport.addEventListener('gesturestart', event => {
      event.preventDefault();
      gestureStartZoom = zoom;
    });
    viewport.addEventListener('gesturechange', event => {
      event.preventDefault();
      zoomAt(gestureStartZoom * event.scale, event.clientX, event.clientY);
    });
    viewport.addEventListener('gestureend', event => event.preventDefault());
    const cards = [...container.querySelectorAll('.tree-node')];
    const edges = [...container.querySelectorAll('.tree-branch')];
    let resolvedPaths = [];
    let filter = {grade: null, hasR: null, pathIndex: null};

    function resolveDisplayPath(path) {
      const cardsOnPath = [];
      const edgesOnPath = [];
      let view = root;
      let model = tree;
      for (const step of path.steps) {
        if (model.id !== step.node) throw new Error(`判断树节点不匹配：${step.node}`);
        const branch = view.branches.get(step.outcome);
        if (!branch) throw new Error(`判断树分支不存在：${step.node}/${step.outcome}`);
        if (step.certainty !== 'certain' && step.certainty !== 'possible') {
          throw new Error(`未知路径确定性：${step.certainty}`);
        }
        cardsOnPath.push(view.card);
        edgesOnPath.push({element: branch.edge, certainty: step.certainty});
        view = branch.child;
        model = branch.model;
      }
      if (!model.result || model.result.grade !== path.grade || model.result.has_r !== path.has_r) {
        throw new Error('判断树终点与结果不一致');
      }
      cardsOnPath.push(view.card);
      return {path, cardsOnPath, edgesOnPath};
    }

    function paint() {
      for (const card of cards) card.classList.remove('is-active');
      for (const edge of edges) edge.classList.remove('is-active', 'certain', 'possible');
      container.classList.toggle('has-paths', resolvedPaths.length > 0);
      let visible = resolvedPaths;
      if (filter.grade !== null) {
        visible = visible.filter(item => item.path.grade === filter.grade && item.path.has_r === filter.hasR);
        if (filter.pathIndex !== null) visible = visible.slice(filter.pathIndex, filter.pathIndex + 1);
      }
      for (const item of visible) {
        for (const card of item.cardsOnPath) card.classList.add('is-active');
        for (const edge of item.edgesOnPath) {
          edge.element.classList.add('is-active', edge.certainty);
        }
      }
    }

    return {
      setZoom,
      fit,
      getZoom() { return zoom; },
      setPaths(paths) {
        // Full pseudocode: validate every supplied path against the tree; retain its
        // backend certainty; reset the filter; repaint the union of reachable routes.
        resolvedPaths = paths.map(resolveDisplayPath);
        filter = {grade: null, hasR: null, pathIndex: null};
        paint();
      },
      setFilter(grade, hasR, pathIndex=null) {
        // Filtering selects displayed routes only. It must never recalculate certainty.
        filter = {grade, hasR, pathIndex};
        paint();
      },
      clearHighlights() {
        resolvedPaths = [];
        filter = {grade: null, hasR: null, pathIndex: null};
        paint();
      }
    };
  }

  window.RuleTree = Object.freeze({create});
})();
