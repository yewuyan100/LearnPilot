import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const debuggerUrl = process.env.CHROME_DEBUG_URL ?? "http://127.0.0.1:9333";
const appRoot = process.env.APP_ROOT ?? "http://127.0.0.1:5173";
const outputDir = process.env.ACCEPTANCE_OUTPUT ?? "../artifacts/visual-redesign-batch-2a/after";
const mode = process.env.ACCEPTANCE_MODE ?? "after";

await mkdir(outputDir, { recursive: true });

async function openTarget(pathname = "/items") {
  const url = new URL(pathname, appRoot).href;
  const response = await fetch(`${debuggerUrl}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
  if (!response.ok) throw new Error(`Cannot create Chrome target: ${response.status}`);
  return response.json();
}

class CdpSession {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.sequence = 0;
    this.pending = new Map();
    this.events = [];
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const entry = this.pending.get(message.id);
        if (!entry) return;
        this.pending.delete(message.id);
        if (message.error) entry.reject(new Error(message.error.message));
        else entry.resolve(message.result);
      } else {
        this.events.push(message);
      }
    });
  }

  async ready() {
    if (this.socket.readyState === WebSocket.OPEN) return;
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
  }

  send(method, params = {}) {
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }

  close() {
    this.socket.close();
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function pause(ms = 250) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(session, selector, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await session.evaluate(`(() => {
      const node = document.querySelector(${JSON.stringify(selector)});
      const text = document.body?.innerText ?? "";
      return document.readyState === "complete"
        && Boolean(node)
        && !text.includes("正在读取")
        && !text.includes("正在整理")
        && !text.includes("正在恢复");
    })()`);
    if (ready) {
      await pause(300);
      return;
    }
    await pause(180);
  }
  throw new Error(`Timed out waiting for ${selector}`);
}

async function navigate(session, path, selector) {
  await session.send("Page.navigate", { url: new URL(path, appRoot).href });
  await waitFor(session, selector);
}

async function setViewport(session, width, height) {
  await session.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 768,
  });
}

async function screenshot(session, name) {
  const shot = await session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
  });
  await writeFile(join(outputDir, `${name}.png`), Buffer.from(shot.data, "base64"));
}

async function pageReport(session, name, width, height) {
  return session.evaluate(`(() => {
    const visible = (node) => {
      if (!node) return false;
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
    };
    const lineCount = (node) => {
      const range = document.createRange();
      range.selectNodeContents(node);
      return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
    };
    const wrapped = [...document.querySelectorAll('a, button, summary')]
      .filter(visible)
      .filter((node) => lineCount(node) > 1)
      .map((node) => node.innerText.trim().replace(/\\s+/g, " "))
      .filter(Boolean);
    return {
      name: ${JSON.stringify(name)},
      width: ${width},
      height: ${height},
      path: location.pathname,
      search: location.search,
      title: document.querySelector('h1')?.innerText.trim() ?? "",
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth,
      wrappedClickables: wrapped,
      dialogOpen: Boolean(document.querySelector('[role="dialog"], dialog[open]')),
      selectedCitation: document.querySelector('.rag-source-detail .citation-chip')?.textContent?.trim() ?? null,
    };
  })()`);
}

const target = await openTarget();
const session = new CdpSession(target.webSocketDebuggerUrl);
await session.ready();
await Promise.all([
  session.send("Page.enable"),
  session.send("Runtime.enable"),
  session.send("Network.enable"),
  session.send("Log.enable"),
]);

const captures = [
  ["planning-index", "/items", ".item-row"],
  ["planning-overview", "/items/1?view=overview", '[data-goal-view="overview"]'],
  ["planning-route", "/items/1?view=route", '[data-goal-view="route"]'],
  ["planning-content", "/items/1?view=content", '[data-goal-view="content"]'],
  ["planning-feedback", "/items/1?view=feedback", '[data-goal-view="feedback"]'],
  ["planning-history", "/items/1?view=history", '[data-goal-view="history"]'],
  ["knowledge-recent", "/knowledge", ".knowledge-overview"],
  ["knowledge-pending", "/knowledge?tab=inbox", ".inbox-page"],
  ["knowledge-notes", "/knowledge?tab=notes&note=1", ".notebook-layout"],
  ["knowledge-materials", "/knowledge?tab=materials", ".materials-embedded"],
  ["knowledge-rag", "/knowledge?tab=qa", ".rag-page"],
];

const reports = [];
await setViewport(session, 1440, 900);
for (const [name, path, selector] of captures) {
  await navigate(session, path, selector);
  await screenshot(session, `${name}-1440x900`);
  reports.push(await pageReport(session, name, 1440, 900));
}

await waitFor(session, ".rag-message--assistant .citation-chip");
const citationClicked = await session.evaluate(`(() => {
  const citation = document.querySelector('.rag-message--assistant .citation-chip');
  citation?.click();
  return citation?.textContent?.trim() ?? null;
})()`);
assert(citationClicked, "No real RAG citation was available to select");
await waitFor(session, ".rag-source-detail");
await screenshot(session, "knowledge-rag-citation-1440x900");
reports.push(await pageReport(session, "knowledge-rag-citation", 1440, 900));

if (mode === "after") {
  const responsive = [
    ["planning-index", "/items", ".item-row"],
    ["planning-feedback", "/items/1?view=feedback", '[data-goal-view="feedback"]'],
    ["knowledge-recent", "/knowledge", ".knowledge-overview"],
    ["knowledge-notes", "/knowledge?tab=notes&note=1", ".notebook-layout"],
    ["knowledge-materials", "/knowledge?tab=materials", ".materials-embedded"],
    ["knowledge-rag", "/knowledge?tab=qa", ".rag-page"],
  ];
  for (const [width, height] of [[768, 1024], [390, 844]]) {
    await setViewport(session, width, height);
    for (const [name, path, selector] of responsive) {
      await navigate(session, path, selector);
      if (name === "knowledge-rag") {
        await waitFor(session, ".rag-message--assistant .citation-chip");
        await session.evaluate("document.querySelector('.rag-message--assistant .citation-chip')?.click()");
        await waitFor(session, ".rag-source-detail");
      }
      await screenshot(session, `${name}-${width}x${height}`);
      reports.push(await pageReport(session, name, width, height));
    }
  }

  await setViewport(session, 1440, 900);
  await navigate(session, "/items", ".item-row");
  const firstGoalOpened = await session.evaluate(`(() => {
    const link = document.querySelector('.item-row h2 a');
    link?.click();
    return Boolean(link);
  })()`);
  assert(firstGoalOpened, "Planning index did not expose an item link");
  await waitFor(session, ".item-detail-tabs");

  const planningViews = [];
  for (const label of ["概览", "路线", "内容", "反馈", "记录"]) {
    const clicked = await session.evaluate(`(() => {
      const button = [...document.querySelectorAll('.item-detail-tabs button')].find((node) => node.textContent.trim() === ${JSON.stringify(label)});
      button?.click();
      return Boolean(button);
    })()`);
    assert(clicked, `Planning tab missing: ${label}`);
    await pause(180);
    planningViews.push(await session.evaluate("document.querySelector('.item-detail-view')?.getAttribute('data-goal-view')"));
  }
  const materialDialogOpened = await session.evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((node) => node.textContent.includes('关联资料'));
    button?.click();
    return Boolean(button);
  })()`);
  assert(materialDialogOpened, "Linked-material dialog trigger missing");
  await waitFor(session, '[role="dialog"], dialog[open]');
  const materialDialog = await session.evaluate(`(() => ({
    open: Boolean(document.querySelector('[role="dialog"], dialog[open]')),
    title: document.querySelector('[role="dialog"] h2, dialog[open] h2')?.textContent?.trim() ?? "",
  }))()`);
  await session.evaluate(`(() => {
    const close = [...document.querySelectorAll('[role="dialog"] button, dialog[open] button')].find((node) => /关闭|取消/.test(node.textContent) || /关闭/.test(node.getAttribute('aria-label') ?? ''));
    close?.click();
  })()`);

  await navigate(session, "/knowledge", ".knowledge-overview");
  const knowledgeTabs = [];
  for (const label of ["最近内容", "待整理", "笔记与摘录", "资料与来源", "基于资料核对"]) {
    const clicked = await session.evaluate(`(() => {
      const button = [...document.querySelectorAll('.knowledge-hub-page > .page-tabs button')].find((node) => node.textContent.trim() === ${JSON.stringify(label)});
      button?.click();
      return Boolean(button);
    })()`);
    assert(clicked, `Knowledge tab missing: ${label}`);
    await pause(450);
    knowledgeTabs.push({ label, search: await session.evaluate("location.search") });
  }

  await navigate(session, "/knowledge?tab=notes&note=1", ".note-editor");
  const noteInteraction = await session.evaluate(`(() => {
    const note = document.querySelector('.note-list-item');
    note?.click();
    const title = document.querySelector('.note-title-input');
    if (title) {
      title.focus();
      const original = title.value;
      window.__acceptanceNoteTitle = original;
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setValue.call(title, original + ' ');
      title.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: ' ' }));
    }
    return { selected: Boolean(note), editable: !title?.disabled, changed: title?.value === window.__acceptanceNoteTitle + ' ' };
  })()`);
  await pause(60);
  noteInteraction.restored = await session.evaluate(`(() => {
    const title = document.querySelector('.note-title-input');
    if (!title) return false;
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setValue.call(title, window.__acceptanceNoteTitle);
    title.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward' }));
    return title.value === window.__acceptanceNoteTitle;
  })()`);
  await pause(60);

  await navigate(session, "/knowledge?tab=materials", ".material-card");
  const materialInteraction = await session.evaluate(`(() => ({
    hasOpen: Boolean(document.querySelector('.material-card__file a')),
    hasLink: [...document.querySelectorAll('.material-card__actions button')].some((node) => node.textContent.includes('关联事项')),
    hasNote: [...document.querySelectorAll('.material-card__actions a')].some((node) => node.textContent.includes('记录笔记')),
    hasDelete: Boolean(document.querySelector('.material-card__actions .icon-button--danger')),
    detailHref: document.querySelector('.material-card__file a')?.getAttribute('href') ?? '',
  }))()`);
  assert(materialInteraction.detailHref, "Material row did not expose its detail view");
  const materialDetailUrl = new URL(materialInteraction.detailHref, appRoot);
  materialDetailUrl.searchParams.set("view", "learning");
  await navigate(session, `${materialDetailUrl.pathname}${materialDetailUrl.search}`, '[data-material-view="learning"]');
  const scopedQaHref = await session.evaluate(`(() => [...document.querySelectorAll('a')]
    .find((node) => node.textContent.includes('限定此资料提问'))?.getAttribute('href') ?? '')()`);
  materialInteraction.hasScopedQa = Boolean(scopedQaHref);
  materialInteraction.scopedQaHref = scopedQaHref;
  assert(materialInteraction.hasScopedQa, "Material detail did not expose scoped RAG");

  await navigate(session, scopedQaHref, ".rag-page");
  await waitFor(session, ".rag-message--assistant .citation-chip");
  const materialScope = await session.evaluate(`(() => ({
    scope: document.querySelector('.rag-scope select')?.value ?? "",
    material: [...document.querySelectorAll('.rag-scope select')].find((node) => node.getAttribute('aria-label')?.includes('资料'))?.value ?? "",
  }))()`);
  await session.evaluate("document.querySelector('.rag-message--assistant .citation-chip')?.click()");
  await waitFor(session, ".rag-source-detail");
  const selectedEvidence = await session.evaluate("document.querySelector('.rag-source-detail .citation-chip')?.textContent?.trim() ?? ''");
  await session.send("Page.reload", { ignoreCache: true });
  await waitFor(session, ".rag-page");
  const refreshState = await session.evaluate(`(() => ({
    path: location.pathname,
    search: location.search,
    scope: document.querySelector('.rag-scope select')?.value ?? "",
  }))()`);
  await session.evaluate("history.back()");
  await pause(500);
  const backState = await session.evaluate("({ path: location.pathname, search: location.search })");

  reports.push({
    interactions: {
      planningViews,
      materialDialog,
      knowledgeTabs,
      noteInteraction,
      materialInteraction,
      materialScope,
      selectedEvidence,
      refreshState,
      backState,
    },
  });
}

const browserErrors = session.events
  .filter((event) => event.method === "Runtime.exceptionThrown"
    || (event.method === "Runtime.consoleAPICalled" && event.params.type === "error"))
  .map((event) => ({ method: event.method, params: event.params }));
const failedRequests = session.events
  .filter((event) => event.method === "Network.loadingFailed" && !event.params.canceled)
  .map((event) => event.params.errorText);

if (mode === "after") {
  for (const report of reports.filter((item) => item.width)) {
    assert(!report.horizontalOverflow, `${report.name} ${report.width}x${report.height}: horizontal overflow`);
  }
  assert(browserErrors.length === 0, "Browser console errors detected");
  assert(failedRequests.length === 0, "Browser network failures detected");
}

const result = {
  mode,
  generatedAt: new Date().toISOString(),
  appRoot,
  reports,
  browserErrors,
  failedRequests,
};
await writeFile(join(outputDir, "browser-acceptance.json"), `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result, null, 2));
session.close();
