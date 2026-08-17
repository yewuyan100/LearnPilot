import { writeFile } from "node:fs/promises";
import { join } from "node:path";

const debuggerUrl = process.env.CHROME_DEBUG_URL ?? "http://127.0.0.1:9333";
const appUrl = process.env.APP_URL ?? "http://127.0.0.1:4173/workspace";
const outputDir = process.env.ACCEPTANCE_OUTPUT ?? "artifacts/learnpilot-redesign";

async function openTarget() {
  const response = await fetch(`${debuggerUrl}/json/new?${encodeURIComponent(appUrl)}`, { method: "PUT" });
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
    const result = await this.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }

  close() {
    this.socket.close();
  }
}

async function waitForWorkbench(session, requiredText, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await session.evaluate(`(() => {
      const text = document.body?.innerText ?? '';
      const focus = document.querySelector('.focus-panel');
      return document.readyState === 'complete'
        && focus?.getAttribute('aria-busy') !== 'true'
        && !text.includes('正在读取下一步')
        && !text.includes('正在读取活动记录')
        && ${JSON.stringify(requiredText)}.every((item) => text.includes(item));
    })()`);
    if (ready) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error("Timed out waiting for the complete LearnPilot workbench");
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

const sizes = [
  [1586, 992],
  [1440, 900],
  [1366, 768],
  [1280, 800],
  [1024, 768],
  [768, 1024],
  [414, 896],
  [390, 844],
  [375, 812],
  [320, 720],
];

const requiredText = [
  "LearnPilot",
  "当前重点",
  "下一步",
  "待处理",
  "最近进展",
  "学习洞察",
  "知识库统计",
  "AI 助手建议",
  "学习活动",
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const reports = [];
for (const [width, height] of sizes) {
  await session.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 768,
  });
  await session.send("Page.navigate", { url: appUrl });
  await waitForWorkbench(session, requiredText);

  const report = await session.evaluate(`(() => {
    const bodyText = document.body.innerText;
    const visible = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return false;
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0 && box.right > 0 && box.left < innerWidth && box.bottom > 0 && box.top < innerHeight;
    };
    const textLineCount = (element) => {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      const tops = new Set();
      while (walker.nextNode()) {
        if (!walker.currentNode.textContent.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(walker.currentNode);
        for (const rect of range.getClientRects()) tops.add(Math.round(rect.top));
      }
      return tops.size;
    };
    const clickableWraps = [...document.querySelectorAll('.nav-link, .mobile-bottom-nav a, button:not(.top-search), .button, .text-link, .panel-link, .top-ai-button')]
      .filter((element) => visibleElement(element))
      .filter((element) => textLineCount(element) > 1)
      .map((element) => element.innerText.trim().replace(/\\s+/g, ' '));
    function visibleElement(element) {
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0 && box.right > 0 && box.left < innerWidth && box.bottom > 0 && box.top < innerHeight;
    }
    const box = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { width: Math.round(rect.width), height: Math.round(rect.height), top: Math.round(rect.top), bottom: Math.round(rect.bottom) };
    };
    const headings = [...document.querySelectorAll('h1, h2, h3')]
      .filter(visibleElement)
      .map((element) => element.innerText.trim());
    return {
      title: document.title,
      location: location.href,
      innerWidth,
      innerHeight,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth,
      sideRailVisible: visible('.side-rail'),
      mobileHeaderVisible: visible('.mobile-header'),
      mobileNavVisible: visible('.mobile-bottom-nav'),
      desktopNavLabels: [...document.querySelectorAll('.side-rail nav .nav-link')].filter(visibleElement).map((item) => item.innerText.trim()),
      mobileNavLabels: [...document.querySelectorAll('.mobile-bottom-nav a')].filter(visibleElement).map((item) => item.innerText.trim()),
      topSearchVisible: visible('.top-search'),
      clock: document.querySelector('.top-bar__clock')?.innerText.trim().replace(/\\s+/g, ' ') ?? '',
      requiredText: ${JSON.stringify(requiredText)}.filter((text) => bodyText.includes(text)),
      headings,
      clickableWraps,
      visualPolish: {
        focus: box('.focus-panel'),
        focusTitleSize: getComputedStyle(document.querySelector('.focus-panel h3')).fontSize,
        illustration: box('.learning-path-illustration'),
        nextSteps: box('.next-steps-panel'),
        pending: box('.pending-panel'),
        pendingEmpty: Boolean(document.querySelector('.pending-panel--empty')),
        learningInsight: box('.learning-insight-card'),
        knowledgeStats: box('.knowledge-stats-card'),
        aiSuggestion: box('.ai-suggestion-card'),
        learningInsightCompact: Boolean(document.querySelector('.learning-insight-card--compact')),
        activityChartPresent: Boolean(document.querySelector('.activity-chart')),
        activityEmptyPresent: Boolean(document.querySelector('.activity-empty-state')),
        summaryRadialCount: [...document.querySelectorAll('.summary-card')].filter((element) => getComputedStyle(element).backgroundImage.includes('radial-gradient')).length,
        aiSuggestionTinted: getComputedStyle(document.querySelector('.ai-suggestion-card')).backgroundImage.includes('radial-gradient'),
      },
    };
  })()`);

  if ([1586, 1440, 1024, 768, 390, 375].includes(width)) {
    const shot = await session.send("Page.captureScreenshot", { format: "png", fromSurface: true });
    await writeFile(join(outputDir, `workspace-${width}x${height}.png`), Buffer.from(shot.data, "base64"));
  }
  reports.push({ width, height, ...report });
}

await session.send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await session.send("Page.navigate", { url: appUrl });
await new Promise((resolve) => setTimeout(resolve, 1200));
const searchBefore = await session.evaluate("Boolean(document.querySelector('.search-overlay'))");
await session.evaluate("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))");
await new Promise((resolve) => setTimeout(resolve, 150));
const searchAfter = await session.evaluate(`(() => ({
  open: Boolean(document.querySelector('.search-overlay')),
  placeholder: document.querySelector('.search-dialog input')?.getAttribute('placeholder') ?? '',
  focused: document.activeElement === document.querySelector('.search-dialog input'),
}))()`);
await session.evaluate("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))");

const navigationSequence = [];
for (const expected of [
  ["学习规划", "/items"],
  ["知识库", "/knowledge"],
  ["AI 协作", "/ai"],
  ["工作台", "/workspace"],
]) {
  const clicked = await session.evaluate(`(() => {
    const link = [...document.querySelectorAll('.side-rail .nav-link')].find((item) => item.innerText.trim() === ${JSON.stringify(expected[0])});
    link?.click();
    return Boolean(link);
  })()`);
  assert(clicked, `Navigation link missing: ${expected[0]}`);
  await new Promise((resolve) => setTimeout(resolve, 900));
  navigationSequence.push(await session.evaluate(`(() => ({
    label: ${JSON.stringify(expected[0])},
    path: location.pathname,
    search: location.search,
    heading: document.querySelector('h1')?.innerText.trim() ?? '',
    goalContext: document.body.innerText.includes('当前事项') && !document.body.innerText.includes('尚未选择事项'),
    materialContext: document.body.innerText.includes('限定到《'),
  }))()`));
}

const routeChecks = [];
for (const expected of [
  ["/items", "学习规划"],
  ["/knowledge", "知识库"],
  ["/explore", "发现"],
  ["/ai", "AI 协作"],
  ["/settings", "设置"],
]) {
  await session.send("Page.navigate", { url: new URL(expected[0], appUrl).href });
  await new Promise((resolve) => setTimeout(resolve, 900));
  routeChecks.push(await session.evaluate(`(() => ({
    path: location.pathname,
    heading: document.querySelector('h1')?.innerText.trim() ?? '',
    title: document.title,
  }))()`));
}

const browserErrors = session.events
  .filter((event) => event.method === "Runtime.exceptionThrown" || event.method === "Log.entryAdded" || (event.method === "Runtime.consoleAPICalled" && event.params.type === "error"))
  .map((event) => ({ method: event.method, params: event.params }));
const failedRequests = session.events
  .filter((event) => event.method === "Network.loadingFailed")
  .map((event) => event.params.errorText);

const result = {
  appUrl,
  generatedAt: new Date().toISOString(),
  reports,
  searchShortcut: { before: searchBefore, after: searchAfter },
  navigationSequence,
  routeChecks,
  browserErrors,
  failedRequests,
};

for (const report of reports) {
  assert(report.title === "LearnPilot", `${report.width}×${report.height}: document title mismatch`);
  assert(report.horizontalOverflow === false, `${report.width}×${report.height}: horizontal overflow detected`);
  assert(report.requiredText.length === requiredText.length, `${report.width}×${report.height}: mandatory workbench text missing`);
  assert(report.clickableWraps.length === 0, `${report.width}×${report.height}: wrapped clickable label detected`);
}
assert(searchBefore === false && searchAfter.open && searchAfter.focused, "Ctrl+K search shortcut failed");
assert(navigationSequence.every((item, index) => item.path === ["/items", "/knowledge", "/ai", "/workspace"][index]), "Shell navigation sequence failed");
const generalAi = navigationSequence.find((item) => item.path === "/ai");
assert(generalAi && generalAi.search === "" && !generalAi.goalContext && !generalAi.materialContext, "General AI route leaked goal or material context");
assert(routeChecks.every((item) => item.path && item.heading && item.title === "LearnPilot"), "Route heading check failed");
assert(browserErrors.length === 0, "Browser console errors detected");
assert(failedRequests.length === 0, "Browser network failures detected");

const desktopPolish = reports.find((item) => item.width === 1440)?.visualPolish;
assert(desktopPolish?.focus && desktopPolish.nextSteps && desktopPolish.focus.height >= desktopPolish.nextSteps.height + 20 && Number.parseFloat(desktopPolish.focusTitleSize) >= 28, "1440: Current Focus is not visually dominant");
assert(desktopPolish?.illustration && desktopPolish.illustration.width >= 180, "1440: learning-path illustration is not sufficiently enlarged");
if (desktopPolish?.pendingEmpty) assert(desktopPolish.pending && desktopPolish.pending.height >= 180 && desktopPolish.pending.height <= 240, "1440: Pending compact state is outside the 180–240px target");
if (desktopPolish?.learningInsightCompact) {
  assert(desktopPolish.learningInsight && desktopPolish.learningInsight.height <= 280, "1440: compact Learning Insight remains too tall");
  assert(!desktopPolish.activityChartPresent && desktopPolish.activityEmptyPresent, "1440: zero activity still renders a chart");
}
assert(desktopPolish?.summaryRadialCount === 4, "1440: summary atmosphere gradients are missing");
assert(desktopPolish?.aiSuggestionTinted, "1440: AI suggestion hierarchy tint is missing");

await writeFile(join(outputDir, "browser-acceptance.json"), `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result, null, 2));
session.close();
