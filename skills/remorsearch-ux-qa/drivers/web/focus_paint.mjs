// Supplemental SM-06 evidence for simple, opaque layers that do not receive
// pointer input. Never change page styles or the ordinary pointer hit test.
const WALK_POINTS = [0.15, 0.5, 0.85].flatMap((x) => [0.2, 0.5, 0.8].map((y) => [x, y]));
const STEP_POINTS = [[0.5, 0.5], [0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]];
const ELEMENT_LIMIT = 2000;
const HIT_NODE_LIMIT = 4;
const LAYER_LIMIT = 8;
const FRAGMENT_LIMIT = 32;
const PROBE_DEADLINE_MS = 350;

// Runs in Chromium; constrain the supplement to simple opaque HTML paint.
// A CDP geometry hit by itself also finds transparent input layers.
function paintSamples({ fractions, limit, layerLimit, expectedId, capture }) {
  const target = document.activeElement;
  const viewport = window.visualViewport;
  if (!(target instanceof HTMLElement) || ['HTML', 'BODY', 'IFRAME'].includes(target.tagName)
      || target.shadowRoot?.activeElement || (expectedId !== null && target.id !== expectedId)
      || !viewport || viewport.scale !== 1 || viewport.offsetLeft || viewport.offsetTop) return null;
  const box = target.getBoundingClientRect();
  const scroll = [window.scrollX, window.scrollY];
  const geometry = [box.x, box.y, box.width, box.height];
  const sameRounded = (values, reference) => values.every((n, i) => Math.round(n * 100) / 100 === reference[i]);
  if (capture && (!sameRounded(geometry, [capture.box.x, capture.box.y, capture.box.w, capture.box.h])
      || !sameRounded(scroll, capture.scroll))) return null;
  if (box.width < 4 || box.height < 4 || box.left < 0 || box.top < 0
      || box.right > viewport.width || box.bottom > viewport.height) return null;

  const tree = document.getElementsByTagName('*');
  if (tree.length > limit) return null;
  const points = fractions.map(([x, y]) => ({ x: box.left + box.width * x, y: box.top + box.height * y }));
  let layers = 0;
  const covered = new Set();
  for (const el of tree) {
    if (!(el instanceof HTMLElement) || el === target || el.contains(target) || target.contains(el)) continue;
    const s = getComputedStyle(el);
    if (s.pointerEvents !== 'none' || (s.position !== 'fixed' && s.position !== 'sticky')
        || s.visibility !== 'visible' || s.opacity !== '1' || !/^rgb\(/.test(s.backgroundColor)) continue;
    const r = el.getBoundingClientRect();
    if (r.right <= box.left || r.bottom <= box.top || r.left >= box.right || r.top >= box.bottom) continue;
    if (++layers > layerLimit) return null;
    for (const p of points) {
      if (p.x >= r.left && p.x < r.right && p.y >= r.top && p.y < r.bottom) covered.add(p);
    }
  }
  return covered.size ? { points: [...covered], box: geometry, scroll, id: target.id } : null;
}

// Runs with the CDP-resolved hit node as this. Recheck the current focus box
// and compositing constraints rather than treating any overlap as paint.
function opaqueHit(expected) {
  const hit = this;
  const target = document.activeElement;
  if (!(hit instanceof HTMLElement) || !(target instanceof HTMLElement) || hit === target || hit.contains(target) || target.contains(hit)) return null;
  const v = window.visualViewport;
  const r = target.getBoundingClientRect();
  if (!v || v.scale !== 1 || v.offsetLeft || v.offsetTop || target.id !== expected.id
      || window.scrollX !== expected.scroll[0] || window.scrollY !== expected.scroll[1]
      || ![r.x, r.y, r.width, r.height].every((val, i) => val === expected.box[i])) return null;
  const s = getComputedStyle(hit);
  if (s.pointerEvents !== 'none' || (s.position !== 'fixed' && s.position !== 'sticky')
      || s.visibility !== 'visible' || !/^rgb\(/.test(s.backgroundColor) || s.backgroundClip !== 'border-box'
      || [s.borderTopLeftRadius, s.borderTopRightRadius, s.borderBottomRightRadius, s.borderBottomLeftRadius].some((x) => x !== '0px')) return null;
  for (let el = hit; el; el = el.parentElement) {
    const a = getComputedStyle(el);
    // Chromium's mask-box-image can hide pixels while the ordinary maskImage
    // reports 'none' and the paint hit test still returns the masked node.
    const vendorMask = a.getPropertyValue('-webkit-mask-box-image-source').trim();
    if ((vendorMask && vendorMask !== 'none') || a.opacity !== '1' || a.transform !== 'none' || a.filter !== 'none' || a.clipPath !== 'none'
        || a.clip !== 'auto' || a.mixBlendMode !== 'normal' || a.maskImage !== 'none'
        || a.scale !== 'none' || a.rotate !== 'none' || a.translate !== 'none'
        || a.contain !== 'none' || a.overflowX !== 'visible' || a.overflowY !== 'visible') return null;
  }
  const related = (el) => el && (el.contains(hit) || hit.contains(el));
  const expanded = [...document.querySelectorAll('[aria-expanded="true"][aria-controls]')].some((el) =>
    (el.getAttribute('aria-controls') || '').split(/\s+/).some((id) => related(document.getElementById(id))));
  const popover = hit.closest('[popover]') || [...hit.querySelectorAll('[popover]')].find((el) => el.matches(':popover-open'));
  // A new paint observation must not create an Escape exemption. Recognized
  // user-opened layers stay on the older focus path, which owns that policy.
  if (expanded || (popover && popover.matches(':popover-open'))) return null;
  // An inline layer can paint one box per line. The enclosing union also
  // contains unpainted gaps, even when every sampled point hit the same node.
  const fragments = hit.getClientRects();
  if (fragments.length > expected.fragmentLimit) return null;
  let coveredArea = 0;
  let full_fragment = false;
  for (const box of fragments) {
    if (!(box.width > 0 && box.height > 0)) continue;
    const overlapX = Math.max(0, Math.min(box.right, r.right) - Math.max(box.left, r.left));
    const overlapY = Math.max(0, Math.min(box.bottom, r.bottom) - Math.max(box.top, r.top));
    // Use one rectangle's intersection rather than adding possibly overlapping
    // fragments. This intentionally understates complex partial coverage.
    coveredArea = Math.max(coveredArea, overlapX * overlapY);
    if (box.left <= r.left && box.right >= r.right && box.top <= r.top && box.bottom >= r.bottom) full_fragment = true;
  }
  if (!coveredArea) return null;
  return { selector: hit.id ? '#' + CSS.escape(hit.id) : hit.localName, full_fragment,
    box_fraction: Math.min(1, coveredArea / (r.width * r.height)) };
}

// The protocol calls are asynchronous. Do not attach a hit from a moved
// viewport or redirected focus to the earlier capture.
function sameFocusGeometry(expected) {
  const target = document.activeElement;
  const v = window.visualViewport;
  if (!(target instanceof HTMLElement) || target.id !== expected.id || target.shadowRoot?.activeElement
      || !v || v.scale !== 1 || v.offsetLeft || v.offsetTop
      || window.scrollX !== expected.scroll[0] || window.scrollY !== expected.scroll[1]) return false;
  const r = target.getBoundingClientRect();
  return [r.x, r.y, r.width, r.height].every((n, i) => n === expected.box[i]);
}

async function measureFocusPaintCover(page, getCdp, { walk = false, domId = null, capture = null }, state) {
  const fractions = walk ? WALK_POINTS : STEP_POINTS;
  try {
    const samples = await page.evaluate(paintSamples, { fractions, limit: ELEMENT_LIMIT, layerLimit: LAYER_LIMIT, expectedId: domId, capture });
    if (!samples || state.expired) return null;
    const cdp = await getCdp();
    if (state.expired) return null;
    const seen = new Map();
    const hitAt = (point) => {
      const key = point.x + ':' + point.y;
      if (!seen.has(key)) {
        if (state.expired) return Promise.reject(new Error('probe deadline'));
        seen.set(key, cdp.send('DOM.getNodeForLocation', { ...point, ignorePointerEventsNone: true }));
      }
      return seen.get(key);
    };
    // DOM.getNodeForLocation uses document CSS coordinates. Geometry and the
    // screenshot use viewport CSS coordinates, including at ordinary scroll.
    const [scrollX, scrollY] = samples.scroll;
    const locations = new Map();
    for (const local of samples.points) {
      const p = { x: Math.floor(local.x + scrollX), y: Math.floor(local.y + scrollY) };
      const key = p.x + ':' + p.y;
      if (locations.has(key)) locations.get(key).weight += 1;
      else locations.set(key, { point: p, weight: 1 });
    }
    const hits = await Promise.all([...locations.values()].map(async ({ point, weight }) =>
      [await hitAt(point), weight]));
    const counts = new Map();
    for (const [{ backendNodeId: id }, weight] of hits) if (id) counts.set(id, (counts.get(id) || 0) + weight);
    if (state.expired || counts.size > HIT_NODE_LIMIT) return null;
    // One known layer supplies the evidence; do not sum uncertain mixed paint.
    const geometry = { id: samples.id, box: samples.box, scroll: samples.scroll };
    for (const [backendNodeId, count] of [...counts].sort((a, b) => b[1] - a[1])) {
      if (state.expired) return null;
      const { object } = await cdp.send('DOM.resolveNode', { backendNodeId });
      if (!object?.objectId) continue;
      try {
        if (state.expired) return null;
        const hit = await cdp.send('Runtime.callFunctionOn', { objectId: object.objectId,
          functionDeclaration: opaqueHit.toString(), arguments: [{ value: { ...geometry, fragmentLimit: FRAGMENT_LIMIT } }], returnByValue: true });
        const paint = hit.result?.value;
        if (state.expired) return null;
        if (!paint) continue;
        let sampleFraction = count / fractions.length;
        let full = false;
        if (sampleFraction === 1 && paint.full_fragment) {
          // The interior grid alone misses a visible rim. Require one opaque
          // layout box to enclose the target and the same top node at its corners.
          const [x, y, w, h] = samples.box;
          const left = x + scrollX, top = y + scrollY;
          const corners = [Math.ceil(left), Math.ceil(left + w) - 1].flatMap((px) =>
            [Math.ceil(top), Math.ceil(top + h) - 1].map((py) => ({ x: px, y: py })));
          const edge = await Promise.all(corners.map(hitAt));
          const coveredEdges = edge.filter((node) => node.backendNodeId === backendNodeId).length;
          full = coveredEdges === corners.length;
          sampleFraction = (count + coveredEdges) / (fractions.length + corners.length);
        }
        const fraction = full ? 1 : Math.min(0.998, Math.round(1000 * Math.min(sampleFraction, paint.box_fraction)) / 1000);
        if (fraction > 0) {
          if (state.expired || !await page.evaluate(sameFocusGeometry, geometry) || state.expired) return null;
          return { selector: paint.selector, user_opened: false, fraction };
        }
      } finally {
        await cdp.send('Runtime.releaseObject', { objectId: object.objectId }).catch(() => {});
      }
    }
  } catch { /* unsupported protocol, stale node, detached frame: retain ordinary evidence */ }
  return null;
}

export async function readFocusPaintCover(page, getCdp, options = {}) {
  const state = { expired: false };
  let timer;
  const timedOut = new Promise((resolve) => {
    timer = setTimeout(() => {
      state.expired = true;
      resolve(null);
    }, PROBE_DEADLINE_MS);
  });
  try {
    return await Promise.race([measureFocusPaintCover(page, getCdp, options, state), timedOut]);
  } finally {
    clearTimeout(timer);
  }
}
