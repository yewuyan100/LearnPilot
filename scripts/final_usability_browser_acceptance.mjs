import fs from "node:fs/promises";
import path from "node:path";

const apiBase = "http://127.0.0.1:8000/api";
const appBase = "http://127.0.0.1:5173";
const debugBase = "http://127.0.0.1:9333";
const outputDir = path.resolve("artifacts/final-usability-closure");

await fs.mkdir(outputDir, { recursive: true });

async function api(pathname, options = {}) {
  const response = await fetch(`${apiBase}${pathname}`, {
    headers: { "content-type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${options.method ?? "GET"} ${pathname} -> ${response.status}: ${await response.text()}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function statusFromNode(pathname) {
  return fetch(`${apiBase}${pathname}`).then((response) => response.status);
}

const runSuffix = Date.now().toString(36);
const firstTitle = `浏览器验收事项 Alpha ${runSuffix}`;
const secondTitle = `浏览器验收事项 Beta ${runSuffix}`;
const renamedGoalTitle = `${firstTitle} · 已重命名`;
const noteTitle = `浏览器验收笔记 ${runSuffix}`;
const renamedNoteTitle = `${noteTitle} · 已重命名`;

const firstGoal = await api("/learning-goals", {
  method: "POST",
  body: JSON.stringify({
    title: firstTitle,
    description: "验证重命名、详情删除与独立资产保留。",
    daily_minutes: 30,
  }),
});
const secondGoal = await api("/learning-goals", {
  method: "POST",
  body: JSON.stringify({
    title: secondTitle,
    description: "用于验证 supporting portfolio 与移动端布局。",
    daily_minutes: 20,
  }),
});
const note = await api("/notes", {
  method: "POST",
  body: JSON.stringify({
    title: noteTitle,
    content_markdown: "## 临时验收\n\n验证唯一标题编辑入口、管理菜单和永久删除。",
    note_type: "study",
    links: [{ entity_type: "learning_goal", entity_id: firstGoal.id }],
  }),
});

let ws;
let sequence = 0;
const pending = new Map();
const consoleErrors = [];
const networkFailures = [];

async function waitForDebugger() {
  const started = Date.now();
  while (Date.now() - started < 20_000) {
    try {
      const targets = await fetch(`${debugBase}/json/list`).then((response) => response.json());
      const target = targets.find((item) => item.type === "page");
      if (target) return target;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Chromium remote debugger did not expose a page target.");
}

const target = await waitForDebugger();
ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve, { once: true });
  ws.addEventListener("error", reject, { once: true });
});

ws.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    if (message.error) request.reject(new Error(JSON.stringify(message.error)));
    else request.resolve(message.result);
    return;
  }
  if (message.method === "Runtime.exceptionThrown") {
    consoleErrors.push(message.params.exceptionDetails?.text ?? "Runtime exception");
  }
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
    consoleErrors.push(message.params.args.map((arg) => arg.value ?? arg.description ?? "").join(" "));
  }
  if (message.method === "Network.responseReceived") {
    const response = message.params.response;
    if (response.status >= 400 && !response.url.endsWith("/favicon.svg")) {
      consoleErrors.push(`${response.status} ${response.url}`);
    }
  }
  if (message.method === "Network.loadingFailed" && !message.params.canceled) {
    networkFailures.push(`${message.params.errorText} (${message.params.type})`);
  }
});

function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const response = await command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.exception?.description ?? response.exceptionDetails.text);
  }
  return response.result.value;
}

async function waitFor(expression, label, timeout = 20_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function navigate(pathname, readyExpression) {
  await command("Page.navigate", { url: `${appBase}${pathname}` });
  await waitFor("document.readyState === 'complete'", `${pathname} document`);
  await waitFor(readyExpression, `${pathname} application`);
}

async function viewport(width, height, mobile = false) {
  await command("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: width,
    screenHeight: height,
  });
}

async function screenshot(filename) {
  const capture = await command("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await fs.writeFile(path.join(outputDir, filename), Buffer.from(capture.data, "base64"));
}

async function clickAria(label) {
  const serialized = JSON.stringify(label);
  const clicked = await evaluate(`(() => {
    const element = document.querySelector('[aria-label=' + CSS.escape(${serialized}) + ']');
    if (!element) return false;
    element.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`Could not click aria-label: ${label}`);
}

async function clickText(label, selector = "button") {
  const serialized = JSON.stringify(label);
  const serializedSelector = JSON.stringify(selector);
  const clicked = await evaluate(`(() => {
    const element = [...document.querySelectorAll(${serializedSelector})]
      .find((candidate) => candidate.textContent.trim() === ${serialized});
    if (!element) return false;
    element.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`Could not click text: ${label}`);
}

async function setInput(ariaLabel, value) {
  const serializedLabel = JSON.stringify(ariaLabel);
  const serializedValue = JSON.stringify(value);
  const updated = await evaluate(`(() => {
    const element = document.querySelector('[aria-label=' + CSS.escape(${serializedLabel}) + ']');
    if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement)) return false;
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, ${serializedValue});
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`);
  if (!updated) throw new Error(`Could not set input: ${ariaLabel}`);
}

await Promise.all([
  command("Page.enable"),
  command("Runtime.enable"),
  command("Network.enable"),
]);

const evidence = {
  appBase,
  isolatedDatabase: true,
  firstGoalId: firstGoal.id,
  secondGoalId: secondGoal.id,
  noteId: note.id,
  checks: [],
  screenshots: [],
  consoleErrors,
  networkFailures,
};

await viewport(1440, 900);
await navigate("/items", `document.querySelector('[aria-label="规划状态和操作"]') && document.body.innerText.includes(${JSON.stringify(firstTitle)})`);
const desktopLayout = await evaluate(`({
  width: innerWidth,
  height: innerHeight,
  hasLegacyTitle: document.body.innerText.includes('规划你的学习旅程'),
  toolbarText: document.querySelector('[aria-label="规划状态和操作"]')?.textContent.trim(),
  horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  focusCount: document.querySelectorAll('.planning-focus').length,
  ledgerCount: document.querySelectorAll('.planning-ledger__item').length,
})`);
evidence.checks.push({ name: "planning-desktop-layout", result: desktopLayout });
await screenshot("planning-1440x900.png");
evidence.screenshots.push("planning-1440x900.png");

await viewport(390, 844, true);
await new Promise((resolve) => setTimeout(resolve, 250));
const mobileLayout = await evaluate(`({
  width: innerWidth,
  height: innerHeight,
  horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  toolbarVisible: Boolean(document.querySelector('[aria-label="规划状态和操作"]')),
})`);
evidence.checks.push({ name: "planning-mobile-layout", result: mobileLayout });
await screenshot("planning-390x844.png");
evidence.screenshots.push("planning-390x844.png");

await viewport(1440, 900);
await new Promise((resolve) => setTimeout(resolve, 200));
await clickAria(`管理事项 ${firstTitle}`);
await waitFor("document.querySelector('[role=menu]')", "item action menu");
await screenshot("item-action-menu.png");
evidence.screenshots.push("item-action-menu.png");
await clickText("重命名", "[role=menuitem]");
await waitFor("document.querySelector('dialog[open]')", "item rename dialog");
await setInput("新的事项名称", renamedGoalTitle);
await screenshot("item-rename-dialog.png");
evidence.screenshots.push("item-rename-dialog.png");
await clickText("保存", "dialog[open] button");
await waitFor(`document.body.innerText.includes(${JSON.stringify(renamedGoalTitle)})`, "renamed item on planning");

await clickText(renamedGoalTitle, "a");
await waitFor(`location.pathname.startsWith('/items/') && document.querySelector('.goal-workspace') && document.body.innerText.includes(${JSON.stringify(renamedGoalTitle)})`, "renamed item detail");
evidence.checks.push({ name: "item-rename-synchronized", result: { path: await evaluate("location.pathname"), title: await evaluate("document.querySelector('.goal-context-header h1')?.textContent.trim()") } });
await clickAria(`管理事项 ${renamedGoalTitle}`);
await clickText("删除事项", "[role=menuitem]");
await waitFor("document.querySelector('dialog[open]') && document.body.innerText.includes('资料、笔记、摘录和回答会保留')", "item delete confirmation");
await screenshot("item-delete-confirmation.png");
evidence.screenshots.push("item-delete-confirmation.png");
await clickText("取消", "dialog[open] button");
await waitFor("!document.querySelector('dialog[open]')", "item delete cancel");
evidence.checks.push({ name: "item-delete-cancel", result: { stillExists: Boolean(await api(`/learning-goals/${firstGoal.id}`)) } });
await clickAria(`管理事项 ${renamedGoalTitle}`);
await clickText("删除事项", "[role=menuitem]");
await waitFor("document.querySelector('dialog[open]')", "reopened item delete confirmation");
await clickText("删除事项", "dialog[open] button");
await waitFor(`location.pathname === '/items' && !document.body.innerText.includes(${JSON.stringify(renamedGoalTitle)})`, "item delete and return");
const deletedGoalStatus = await statusFromNode(`/learning-goals/${firstGoal.id}`);
const preservedNote = await api(`/notes/${note.id}`);
evidence.checks.push({
  name: "item-delete-detail-return-and-preservation",
  result: { path: await evaluate("location.pathname"), deletedGoalStatus, notePreserved: preservedNote.id === note.id, noteLinksRemoved: preservedNote.links.length === 0 },
});

await navigate(`/notes?note=${note.id}`, `document.querySelector('[aria-label="笔记标题"]')`);
await setInput("笔记标题", renamedNoteTitle);
await screenshot("note-rename-state.png");
evidence.screenshots.push("note-rename-state.png");
await waitFor(`document.querySelector('[aria-label=' + CSS.escape(${JSON.stringify(`管理笔记 ${renamedNoteTitle}`)}) + ']')`, "renamed note management action", 10_000);
const savedNote = await api(`/notes/${note.id}`);
evidence.checks.push({ name: "note-canonical-title-rename", result: { title: savedNote.title, duplicateRenameAction: await evaluate("[...document.querySelectorAll('[role=menuitem]')].some((item) => item.textContent.trim() === '重命名')") } });
await clickAria(`管理笔记 ${renamedNoteTitle}`);
await waitFor("document.querySelector('[role=menu]')", "note action menu");
await screenshot("note-action-menu.png");
evidence.screenshots.push("note-action-menu.png");
await clickText("删除笔记", "[role=menuitem]");
await waitFor("document.querySelector('dialog[open]') && document.body.innerText.includes('关联事项和资料本身不会被删除')", "note delete confirmation");
await screenshot("note-delete-confirmation.png");
evidence.screenshots.push("note-delete-confirmation.png");
await clickText("取消", "dialog[open] button");
await waitFor("!document.querySelector('dialog[open]')", "note delete cancel");
evidence.checks.push({ name: "note-delete-cancel", result: { stillExists: Boolean(await api(`/notes/${note.id}`)) } });
await clickAria(`管理笔记 ${renamedNoteTitle}`);
await clickText("删除笔记", "[role=menuitem]");
await waitFor("document.querySelector('dialog[open]')", "reopened note delete confirmation");
await clickText("删除笔记", "dialog[open] button");
await waitFor(`!document.body.innerText.includes(${JSON.stringify(renamedNoteTitle)})`, "note delete success");
const deletedNoteStatus = await statusFromNode(`/notes/${note.id}`);
evidence.checks.push({ name: "note-delete-success", result: { deletedNoteStatus } });

await navigate("/items", `document.body.innerText.includes(${JSON.stringify(secondTitle)})`);
await clickAria(`管理事项 ${secondTitle}`);
await clickText("删除事项", "[role=menuitem]");
await waitFor("document.querySelector('dialog[open]')", "temporary item delete confirmation");
await clickText("删除事项", "dialog[open] button");
await waitFor(`!document.body.innerText.includes(${JSON.stringify(secondTitle)})`, "second temporary item deletion");
const deletedSecondGoalStatus = await statusFromNode(`/learning-goals/${secondGoal.id}`);
evidence.checks.push({ name: "temporary-data-cleanup", result: { deletedSecondGoalStatus } });

evidence.finalPath = await evaluate("location.pathname + location.search");
evidence.consoleErrors = [...new Set(consoleErrors.filter(Boolean))];
evidence.networkFailures = [...new Set(networkFailures.filter(Boolean))];
await fs.writeFile(path.join(outputDir, "browser-acceptance.json"), `${JSON.stringify(evidence, null, 2)}\n`);
ws.close();

if (evidence.consoleErrors.length || evidence.networkFailures.length) {
  throw new Error(`Browser acceptance recorded errors: ${JSON.stringify({ consoleErrors: evidence.consoleErrors, networkFailures: evidence.networkFailures })}`);
}

console.log(JSON.stringify(evidence, null, 2));
