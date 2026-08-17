# LearnPilot Design System

LearnPilot 是面向单人用户的个人学习与知识工作空间。界面首先回答“我正在推进什么、下一步做什么、AI 有什么建议”，再提供知识整理、练习与复盘能力。所有目标、行动、资料和反馈都来自真实 API；无数据时说明原因，不制造演示指标。

## System

- Genre · modern-minimal
- Macrostructure · locked Workbench shell with distinct Planning Portfolio, Knowledge Asset Workspace, Editorial Discovery Canvas and Context Collaboration Stage
- Theme · studied-DNA from the approved LearnPilot reference (Harbor + Ocean Mist token family)
- Axes · cool blue-gray paper / quiet sans typography / restrained deep-ocean-blue accent
- Product path · 工作台 → 学习规划 → 知识库 → 发现 → AI 协作 → 设置

## Information architecture

| 层级 | 页面 | 职责 |
| --- | --- | --- |
| 主导航 | 工作台 | 聚合一个当前行动、后续行动、需要处理与最近变化 |
| 主导航 | 学习规划 | 按用户想达成的结果组织路线、行动、资料、反馈与 AI 建议 |
| 主导航 | 知识库 | 组织真实资料、笔记、AI 整理内容及其学习规划关联 |
| 主导航 | 发现 | 为外部资料、技术趋势、研究结果和推荐保留诚实入口 |
| 主导航 | AI 协作 | 围绕学习规划承载解释辅导、资料研究与推进协作 |
| 主导航 | 设置 | 管理模型、运行状态和安全信息 |
| 次级入口 | 今日安排、路线编辑、复习、成长复盘 | 保留既有能力，不占据一级导航 |

## Visual language

- 一级工作区使用 Ocean Mist：App Canvas `#EEF4F7`、Workspace Canvas `#F4F8FA`、Paper `#FCFDFD`、Mist `#E6F1F7`、Selected Ocean `#DCECF8`。
- 页面使用冷调近白底，主表面不是纯白；Knowledge 的来源与证据允许 Soft Sand，AI Context 使用 Mist Teal；阴影只表达真实层级。
- 深海蓝只用于主操作、选中状态、进度、链接和焦点；成功、警告、危险色只传达语义。
- 不使用整页渐变、玻璃拟态、发光阴影、荧光色、渐变文字或无语义装饰。
- 只使用 Lucide 单色线性图标；不使用 emoji、机器人形象或用户头像。一级导航只显示文字，不使用图标；应用栏和侧栏均不得保留头像占位。
- 信息密度通过分隔线、留白和列宽建立，不堆叠卡片，也不把所有文本做成胶囊。

## Typography

- Display · Geist 700；中文回退 Microsoft YaHei UI。
- Body · IBM Plex Sans 400/600；中文回退 Microsoft YaHei UI。
- Mono · JetBrains Mono，只用于代码内容。
- 正文基准 16px、行高至少 1.55；数字列启用 tabular numbers；标题不用斜体或渐变。

## Components and geometry

- 4pt 间距体系；输入和卡片采用 6–14px 克制圆角。
- 内容最大宽度 92rem；侧栏固定 14rem；顶部栏 4.25rem。
- 事项页按下一步 / 行动路线 / 关联内容 / 最近变化与建议自然分段；高级路线编辑保留为次级入口。
- 一级导航已经表达页面身份，Planning、Knowledge、Discover、AI Collaboration 的 Canvas 不再重复导航名称 H1。
- Planning 使用焦点事项 + supporting ledger；Knowledge 使用 compact view switcher + status runway + content stage；Discover 使用无卡片 editorial canvas；AI 使用 context surface + action menu + conversation stage。
- Notes 在桌面使用 List + Main Editor，移动端编辑器优先；Materials 以资料库为主，上传是按需展开的主操作；RAG 保留会话、回答、引用三列业务对象。
- 统一使用 AppLayout、PageHeader、DashboardCard、EmptyState、Status、Progress、Search、Dialog、Error 和 Loading 组件语汇。
- 所有交互目标最小 44px，焦点环立即可见，状态切换不改变边框宽度。

## Interaction and responsive rules

- Ctrl/Cmd+K 聚焦全局搜索，Escape 退出搜索；项目页签支持方向键切换。
- 一级导航固定为工作台、学习规划、知识库、发现、AI 协作、设置，桌面与移动端顺序一致。
- 60rem 以下切换为移动布局与底部六项文字导航；多列内容依序收为单列。
- 48rem 以下 Knowledge 功能切换器收为单一 dropdown；业务对象列表可以保留，但不新增永久二级导航。
- 1440、1280、1024、768 和 390 宽度不得横向溢出；固定控制区在触屏保持等价操作。
- 动效只用于短促的颜色、位移、侧栏和对话框反馈；`prefers-reduced-motion` 下关闭非必要动画。

## Honesty and content contract

- 目标、任务、时长、资料、掌握度、问答、笔记、诊断和复盘均来自现有 API。
- 无数据时解释原因并给出一个真实可执行的下一步；不得填充示例进度、虚构统计或伪造 AI 回复。
- UI 不显示 LangGraph、Planner、Node、Tool Call、Prompt、Raw JSON、Checkpoint、内部来源 ID 或调试面板。
- 保留既有路由、查询键、幂等保护、发布/回滚、资料重处理、诊断与计划等业务能力。

## Canonical source

[`tokens.css`](tokens.css) 是唯一 Token 真源。页面样式只引用命名 Token，不在组件中临时发明颜色。

## Exports

### CSS source of truth

```css
@import "tokens.css";
/* Harbor + Ocean Mist 的完整颜色、字体、间距、圆角、阴影、动效与层级 Token 位于 tokens.css。 */
```

### Tailwind v4 `@theme`

```css
@theme {
  --color-page: oklch(97.4% 0.009 235);
  --color-surface: oklch(99.4% 0.005 235);
  --color-surface-muted: oklch(96.4% 0.012 235);
  --color-rule: oklch(91.5% 0.013 235);
  --color-muted: oklch(54% 0.025 240);
  --color-ink: oklch(24% 0.032 248);
  --color-primary: oklch(51% 0.16 250);
  --color-primary-hover: oklch(46% 0.15 250);
  --color-focus: oklch(55% 0.17 245);
  --color-workspace-app-canvas: #eef4f7;
  --color-workspace-canvas: #f4f8fa;
  --color-workspace-paper: #fcfdfd;
  --color-workspace-mist: #e6f1f7;
  --color-workspace-selected: #dcecf8;
  --color-workspace-graphite: #17232e;
  --color-workspace-secondary: #60717f;
  --color-workspace-ocean: #0873b9;
  --color-workspace-ocean-dark: #07598e;
  --color-workspace-teal: #e3f2ef;
  --color-workspace-sand: #f3eee4;
  --font-display: "Geist", "Microsoft YaHei UI", ui-sans-serif, sans-serif;
  --font-body: "IBM Plex Sans", "Microsoft YaHei UI", ui-sans-serif, sans-serif;
  --spacing-3xs: 0.125rem;
  --spacing-2xs: 0.25rem;
  --spacing-xs: 0.5rem;
  --spacing-sm: 0.75rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2.5rem;
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-md: 1.125rem;
  --text-lg: 1.375rem;
  --text-xl: 1.75rem;
  --radius-card: 0.875rem;
  --radius-input: 0.625rem;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
}
```

### DTCG `tokens.json`

```json
{
  "$schema": "https://design-tokens.github.io/community-group/format/",
  "color": {
    "page": { "$value": "oklch(97.4% 0.009 235)", "$type": "color" },
    "surface": { "$value": "oklch(99.4% 0.005 235)", "$type": "color" },
    "surface-muted": { "$value": "oklch(96.4% 0.012 235)", "$type": "color" },
    "rule": { "$value": "oklch(91.5% 0.013 235)", "$type": "color" },
    "muted": { "$value": "oklch(54% 0.025 240)", "$type": "color" },
    "ink": { "$value": "oklch(24% 0.032 248)", "$type": "color" },
    "primary": { "$value": "oklch(51% 0.16 250)", "$type": "color" },
    "focus": { "$value": "oklch(55% 0.17 245)", "$type": "color" },
    "workspace": {
      "app-canvas": { "$value": "#eef4f7", "$type": "color" },
      "canvas": { "$value": "#f4f8fa", "$type": "color" },
      "paper": { "$value": "#fcfdfd", "$type": "color" },
      "mist": { "$value": "#e6f1f7", "$type": "color" },
      "selected": { "$value": "#dcecf8", "$type": "color" },
      "graphite": { "$value": "#17232e", "$type": "color" },
      "secondary": { "$value": "#60717f", "$type": "color" },
      "ocean": { "$value": "#0873b9", "$type": "color" },
      "ocean-dark": { "$value": "#07598e", "$type": "color" },
      "teal": { "$value": "#e3f2ef", "$type": "color" },
      "sand": { "$value": "#f3eee4", "$type": "color" }
    }
  },
  "font": {
    "display": { "$value": "Geist, Microsoft YaHei UI, ui-sans-serif, sans-serif", "$type": "fontFamily" },
    "body": { "$value": "IBM Plex Sans, Microsoft YaHei UI, ui-sans-serif, sans-serif", "$type": "fontFamily" }
  },
  "space": {
    "xs": { "$value": "0.5rem", "$type": "dimension" },
    "sm": { "$value": "0.75rem", "$type": "dimension" },
    "md": { "$value": "1rem", "$type": "dimension" },
    "lg": { "$value": "1.5rem", "$type": "dimension" },
    "xl": { "$value": "2.5rem", "$type": "dimension" }
  },
  "duration": {
    "micro": { "$value": "120ms", "$type": "duration" },
    "short": { "$value": "220ms", "$type": "duration" },
    "long": { "$value": "320ms", "$type": "duration" }
  }
}
```

### shadcn/ui variables

```css
:root {
  --background: 97.4% 0.009 235;
  --foreground: 24% 0.032 248;
  --card: 99.4% 0.003 235;
  --card-foreground: 24% 0.032 248;
  --popover: 99.4% 0.003 235;
  --popover-foreground: 24% 0.032 248;
  --primary: 51% 0.16 250;
  --primary-foreground: 99% 0.005 240;
  --secondary: 96.4% 0.012 235;
  --secondary-foreground: 42% 0.03 240;
  --muted: 91.5% 0.013 235;
  --muted-foreground: 54% 0.025 240;
  --accent: 51% 0.16 250;
  --accent-foreground: 99% 0.005 240;
  --destructive: 61% 0.14 24;
  --destructive-foreground: 99% 0.005 240;
  --border: 91.5% 0.013 235;
  --input: 91.5% 0.013 235;
  --ring: 55% 0.17 245;
  --lp-workspace-background: #f4f8fa;
  --lp-workspace-card: #fcfdfd;
  --lp-workspace-muted: #e6f1f7;
  --lp-workspace-selected: #dcecf8;
  --lp-workspace-accent: #0873b9;
  --lp-workspace-teal: #e3f2ef;
  --lp-workspace-sand: #f3eee4;
  --radius: 0.625rem;
}
```
