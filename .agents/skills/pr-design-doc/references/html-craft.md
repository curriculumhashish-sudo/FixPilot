<a id="html-craft---how-to-build-the-page"></a>

# HTML-craft - 如何构建页面

每个展示维度的共享工艺。 一个独立的、离线的社论 HTML 页面，包含手绘 SVG 图形和基于代码的声明。

<a id="the-look-editorial-document-light-theme"></a>

## 外观（编辑文档，浅色主题）

平静、可读、像文档一样——而不是黑暗的仪表板。 骨架：

```html
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{Title}}</title>
<style>
  :root{
    /* single source of truth - prose AND inline-SVG fills both read these (see SVG section) */
    --fg:#1a1a1a; --muted:#5a5a5a; --subtle:#8a8a82;      /* 3 text weights: title · detail · sublabel */
    --bg:#fdfdfb; --card:#ffffff; --elevated:#f7f6f1;     /* page · node fill · raised band/pill */
    --accent:#2b4eaa; --accent-soft:#e6ecfa;
    --rule:#e2e2dc; --rule-strong:#bdbcb4;                /* hairline · emphasized border */
    --code-bg:#f3f1ec; --warn:#b25b0e; --ok:#2f7a3a; --crit:#a02020;
    --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Helvetica,Arial,sans-serif;
  }
  *{box-sizing:border-box} html,body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans)}
  body{line-height:1.6;font-size:16px}
  .wrap{display:grid;grid-template-columns:240px minmax(0,1fr);gap:48px;max-width:1180px;margin:0 auto;padding:32px 28px 96px}
  nav.toc{position:sticky;top:24px;align-self:start;font-size:13px}
  nav.toc h2{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
  nav.toc ol{list-style:none;padding:0;margin:0;counter-reset:toc}
  nav.toc li{counter-increment:toc;margin:4px 0}
  nav.toc li::before{content:counter(toc) ". ";color:var(--muted)}
  nav.toc a{color:var(--fg);text-decoration:none} nav.toc a:hover{color:var(--accent)}
  header.title{border-bottom:1px solid var(--rule);padding-bottom:22px;margin-bottom:28px}
  header.title .eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
  header.title h1{font-size:34px;margin:6px 0 4px;letter-spacing:-.01em}
  header.title .sub{color:var(--muted);max-width:740px}
  h2{font-size:22px;margin:44px 0 10px} h2 .num{color:var(--muted);font-weight:500;margin-right:8px}
  h3{font-size:16px;margin:22px 0 8px}
  code{font-family:var(--mono);font-size:.88em;background:var(--code-bg);padding:1px 5px;border-radius:3px}
  pre{font-family:var(--mono);font-size:13px;background:var(--code-bg);padding:14px 16px;border-radius:6px;overflow-x:auto;border:1px solid var(--rule)}
  pre code{background:transparent;padding:0}
  .kw{color:#7048a8}.str{color:var(--ok)}.com{color:var(--subtle);font-style:italic}
  table{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0}
  th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
  th{font-weight:600;background:var(--code-bg)}
  .callout{border-left:3px solid var(--accent);background:var(--accent-soft);padding:10px 14px;margin:14px 0;border-radius:0 4px 4px 0;font-size:14.5px}
  .callout.warn{border-color:var(--warn);background:#fbf1e6} .callout.note{border-color:var(--muted);background:#f3f1ec}
  .fig{margin:18px 0 22px}
  .fig svg{display:block;max-width:100%;height:auto;background:#fff;border:1px solid var(--rule);border-radius:6px}
  .fig figcaption{font-size:13px;color:var(--muted);margin-top:6px;text-align:center}
  a.src{font-family:var(--mono);font-size:12px;color:var(--accent);text-decoration:none;border-bottom:1px dotted var(--accent)}
  details{border:1px solid var(--rule);border-radius:6px;margin:12px 0}
  details>summary{cursor:pointer;padding:8px 12px;color:var(--muted);font-size:13px;list-style:none}
  details>summary::-webkit-details-marker{display:none}
  details>summary::before{content:"▸ "} details[open]>summary::before{content:"▾ "}
  .ba{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
  @media(max-width:760px){.wrap{grid-template-columns:1fr}.ba{grid-template-columns:1fr}}
</style></head><body>
<div class="wrap">
  <nav class="toc"><h2>Contents</h2><ol>
    <li><a href="#sec1">…</a></li>
  </ol></nav>
  <main>
    <header class="title"><div class="eyebrow">{{kind}}</div><h1>{{Title}}</h1>
      <p class="sub">{{one-paragraph mental model - the big picture in 2-3 sentences}}</p></header>
    <section id="sec1"><h2><span class="num">1</span>…</h2> … </section>
  </main>
</div></body></html>
```

编号粘性 TOC + 顶部的一段心理模型 + 正文部分。 不需要JS
for this shell.

<a id="first-screen-15-second-orientation"></a>

## 第一个屏幕：15 秒定向

读者的注意力是预算。 第一个视口应回答四个问题，无需完整阅读：

1. **这是什么？**标题副标题中的一段心理模型。
2. ** 为什么它很重要？** 顶部附近的 `★` 标注中影响最大的结论、风险或行动。
3. **我应该跳到哪里？**一个编号的便利贴TOC，其标签包含信息，而不仅仅是类别。
4. **为什么我应该信任它？**第一个实质性声明的附近源链接（`path:line`、测试、命令、提交或测试夹具）。

不要以“我读了这些文件”或按时间顺序排列的工作日志打开。 从读者的决定开始：发生了什么变化，系统如何工作，什么路径重要，或者下一步看哪里。 将方法、命令输出和原始差异放在 `<details>` 后面，除非它们是报告的重点。

<a id="skimmable-structure"></a>

## 可略读结构

设计页面，以便忙碌的读者可以在选择深入之前浏览标题、说明文字、标注和表格：

- **标题提出主张。**当该部分有特定发现时，优先选择“仅跨队列写入”而不是“架构”。 仅当标题/副标题已包含发现结果时，通用标签才可接受。
- **一段，一个判断。**保持段落简短； 当一个句子开始证明不同的观点时就分裂。
- **平行点数。**如果你说“三个规则”或“两个风险”，请给它们编号，以便读者可以将声明与列表进行核对。
- **仅对稳定的比较轴使用表格。**表格应该减少认知工作，而不是将微妙的判断强加在整齐的盒子里。
- **使字幕发挥作用。**标题说明了该图的要点，而不仅仅是其类型。

<a id="callouts-give-them-semantic-types"></a>

## 标注（给它们语义类型）

`.callout` / `.callout.warn` / `.callout.note` 样式不可互换 - 为每个样式分配一个固定的工作，读者学会浏览它们：

- **`★` 关键要点**（重音） - 一节中唯一的承载句子。 每节最多一个； 这是读者在不读其他内容的情况下应该记住的内容。
- **`ⓘ` note**（`.note`，静音） - 一个数字的阅读提示，旁白，“为什么我们这样做”，不在关键路径上。
- **`⚠`警告**（`.warn`）-边界，风险，陷阱，约束检查：信任边界，“这确实不做X”，“永远不要提交机密”。 为会咬人的东西保留它。

不要让标注成为壁纸 - 如果每个段落都是一个彩色框，那么其中 None 就具有分量。 字形前缀 (`★ ⓘ ⚠`) 使类型在读者解析文本之前清晰可辨。

<a id="hand-drawn-svg-figures-the-diagrams-that-carry-the-argument"></a>

## 手绘SVG图（带有论点的图）

绘制定制的内联 `<svg viewBox="0 0 W H">`，其中 `<defs>` 用于箭头标记和范围 `<style>`。 您将每个框→之前/之后保持对齐、清晰，并且增量是明确无误的。 语义类别系统：

```html
<svg viewBox="0 0 960 460" role="img" aria-labelledby="f1-t f1-d">
 <title id="f1-t">moduleA call path - before vs after</title>
 <desc id="f1-d">Old direct call is replaced by a routed path through the new resolver.</desc>
 <defs>
  <!-- 每种语义颜色一个标记； 标记填充读取页面调色板-->
  <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 Z" fill="var(--subtle)"/></marker>
  <marker id="arr-chg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 Z" fill="var(--warn)"/></marker>
  <!-- 对人物主题的盒子进行微妙的“升高”清洗-->
  <linearGradient id="subj" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="var(--accent)" stop-opacity=".10"/>
    <stop offset="1" stop-color="var(--accent)" stop-opacity=".02"/></linearGradient>
  <style>
    /* every fill/stroke is a --token: the palette lives once, in :root - prose & figures can't drift */
    .existing{fill:var(--code-bg);stroke:var(--subtle);stroke-width:1.4;stroke-dasharray:5 3} /* before */
    .ex-title{font:700 13px var(--sans);fill:var(--muted)} .ex-detail{font:11.5px var(--mono);fill:var(--subtle)}
    .new{fill:var(--accent-soft);stroke:var(--accent);stroke-width:2}                         /* after / added */
    .new-title{font:800 13px var(--sans);fill:var(--accent)} .detail{font:11.5px var(--mono);fill:var(--fg)}
    .edge{stroke:var(--subtle);stroke-width:1.5;stroke-dasharray:5 3;fill:none}
    .edge-chg{stroke:var(--warn);stroke-width:1.8;fill:none;stroke-dasharray:5 3}             /* the delta */
    .lbl{font:600 10.5px var(--mono);fill:var(--accent)} .gap{font:700 11.5px var(--mono);fill:var(--warn)}
  </style>
 </defs>
 <!-- =====之前：直接调用===== -->
 <g>
  <rect class="existing" x="40" y="60" width="180" height="74" rx="6"/>
  <text class="ex-title"  x="130" y="90"  text-anchor="middle">moduleA.fn()</text>
  <text class="ex-detail" x="130" y="110" text-anchor="middle">old behavior · a.py:42</text>
 </g>
 <!-- ===== 之后：路由呼叫（更改）===== -->
 <g>
  <rect class="new" x="300" y="60" width="180" height="74" rx="6"/>
  <text class="new-title" x="390" y="90" text-anchor="middle">moduleA.fn()</text>
  <path class="edge-chg" d="M220,97 L300,97" marker-end="url(#arr-chg)"/>
  <!-- 药丸位于边缘标签后面，因此在线上仍清晰可见-->
  <rect x="236" y="79" width="48" height="16" rx="5" fill="var(--elevated)" stroke="var(--rule)"/>
  <text class="gap" x="260" y="91" text-anchor="middle">new path</text>
 </g>
</svg>
```

**该骨架中的五个工艺动作 - 它们使人物看起来像设计好的一样
图表而不是草图：**
- **驱动`var(--token)`.**中的每个填充/描边在`:root`中定义一次调色板； SVG 引用了它。 事实的一个来源 - 散文和图表保持同步，调色板调整重排每个图表。 切勿将原始六角形粘贴到图形中。
- **三个文本粗细，始终是相同的三个。** `--fg` 为节点标题（真实符号），
  `--muted` 表示详细信息行，`--subtle` 表示子标签/`path:line`。 眼睛无需阅读即可对层次结构进行排序。 临时混合权重会让图表看起来很嘈杂。
- **`<title>` + `<desc>` 与 `aria-labelledby`.**不是装饰：它是人物自己的记录标题（屏幕阅读器，以及人物声称的自我注释）。
- **梯度清洗标记了主题。**图中的一个容器 *about* 得到
  `#subj`洗（重音10%→2%）； 其他一切都很平淡。 在阅读一个单词之前，读者的目光会落在主角身上。
- **`<g>` 个群组 + `<!-- section -->` 个评论 + 边缘标签药丸。**作者 SVG 喜欢
  代码：每个逻辑单元一个 `<g>`，一个命名它的注释，以及任何后面的一个小 `rect` 药丸
  位于一条线上的标签（边缘上的裸标签会变成糊状）。 当您修改布局三次后，它仍然可编辑。

**编码前后（一致使用）：**
- **灰色虚线**（`.existing`、`.edge`静音）= 之前的内容/未更改的上下文。
- **实心重音** (`.new`) = 此更改添加的内容/后状态。
- **橙色虚线** (`.edge-chg`, `.gap`) = *delta* - 新的/更改的流，正在填充的间隙。 这才是眼睛应该关注的地方。

节点框带有 ** 标题（真实符号）+ 详细信息行（行为 + `file:line`）**，因此该图已经半接地到代码。

显示之前/之后的两种方式：
1. **并排的图表**在`.ba`网格中 - `<figure>`“Before”| `<figure>`“After”。 当布局差异很大时最好。
2. **一个重叠图** - 现有节点为灰色虚线，新节点/边为实线 + 橙色增量，位于同一坐标空间中。 最好的变化是*附加*到现有结构（最清晰的“新增内容”阅读）。

<a id="caption-every-figure-and-hint-how-to-read-the-hard-ones"></a>

## 给每个图加上标题，并提示如何阅读困难的图

没有标题的图会让读者对你的意图进行逆向工程。 两个廉价的习惯可以解决这个问题：

- **`<figcaption>` 说明要点，而不是标签。**不是“架构图”-
  *“请求永远不会直接接触数据库； 每次写入都会经过队列。”* 标题
  这是你指着图说的一句话。 将它们编号 (`Fig 3 ·`) 并
  **图之间的交叉引用**（`state machine in Fig 2`，`evolve timing in Fig 5`）所以
  一份多数字报告读起来就像是不同高度的一个系统，而不是五张松散的图片。
- **对于一个非显而易见的惯例，添加一句话的阅读提示** in a `.callout.note` 在旁边，命名解锁它的唯一事物： *每支箭都进入或离开巴士 - 没有智能体-智能体因为协议是“读写总线”。* 一句话说 *如何查看* 节省读者一秒钟的眯眼。 当可能时，把提示放在图中 `→ §3.2 / Fig 2` 斜杠（单横杠）将图片转换为目录。

<a id="ground-every-claim-to-code-clickable"></a>

## 依据代码的每一个声明（可点击）

人类无法验证的图片是一种责任。 使声明可删除至来源：

- 显式解析两个存储库 Web 库。 对于分叉PR，前状态证据属于基础存储库和合并基础SHA； 后态证据属于 head 存储库并经过验证的 head SHA。 查询每个
  `gh repo view <owner>/<repo> --json url`，然后将链接构建为
  `https://github.com/<o>/<r>/blob/<sha>/<path>#L<n>`. 删除的文件必须链接到 merge-base 处的基础存储库 SHA； 新添加的文件没有之前状态链接。
- 将节点详细信息行、部分文本和每个组件“源”链接中的位置渲染为 `<a class="src" href="{{blobURL}}">path:line</a>`。
- 规则：如果一个盒子不能绑定到符号+位置，那么它就是一个 * 概念 * 盒子 - 对其进行不同的样式并如此说； 不要伪造链接。
- 将证据放在其支持的主张旁边。 读者不必滚动到参考书目来验证行为陈述、优势、风险、指标或测试结果。
- 当行为必须观察时，命令被视为证据：在声明附近显示命令和相关结果，如果噪音，则将详细日志折叠。

<a id="grounding-discipline-borrowed-from-deepwiki"></a>

### 接地纪律（借用DeepWiki）

DeepWiki 风格的 wiki 强制接地 - 值得复制：

- **每个部分的源清单。**打开每个主要部分/组件卡，其中包含其构建的确切文件的小折叠列表：
  `<details><summary>Sources</summary> path/a.py · path/b.py …</details>`. 读者在相信该主张之前先了解该主张的依据。
- **在每个实质性主张、图表、表格和片段后引用。**内联格式：
  `Sources: [path:start-end]`（范围）或 `[path:line]`（单个），允许多个。 没有引用的部分是一种味道——要么磨碎它，要么剪掉它。
- **仅来自代码。 不要胡编乱造。** 每个陈述、方框、边和数字都必须来自你实际阅读的文件，而不是从“相似系统通常如何工作”的角度。如果代码中没有重要的东西，要明确指出，而不是猜测。 将真正的推论标记为推论。
- **广度检查。**如有必要，请根据PR做出决定。 一个只引用1-2个文件的“全面”页面很可能肤浅 - 将相关的文件（调用者、被调用者、配置、测试）拉进来，直到画面真实。

<a id="code-excerpts-when-shown"></a>

## 代码摘录（如果显示）

保持简短并使用跨度手动突出显示（无 JS 突出显示）：换行关键字
`<span class="kw">`、字符串 `<span class="str">`、注释 `<span class="com">`。
**在换行之前对插入上下文进行转义 ** - 源文本不受信任。 在文字中
节点，转义 `&`, `<`, and `>`. 在引号中 HTML 或 SVG 此外，需要转义 `"` as `&quot;` 和 `'` as `&#39;`; 始终引用属性。 对于源 URLs百分号编码动态的所有者、仓库和引用 URL 路径片段。 分别编码每个源路径段，并重新连接 `/`. 然后属性-转义完成的 URL. 将长的差异/代码放在里面 `<details>` (展开) 将每个源生成的值都进行脱逃 HTML 或 SVG包括标题、符号名称、路径、标签、链接文本和属性值。 切勿将源自源的文本视为标记。

<a id="self-contained"></a>

## 独立的

- 一个 `.html` 文件。 内联所有 CSS 和 SVG。 没有构建，没有框架。
- 没有外部脚本、样式、字体、图像或其他资源。 除了打破离线使用之外，第三方活动内容还可以读取和泄露本地打开的私有设计文档。

<a id="mermaid-quick--auxiliary-only"></a>

## 美人鱼（仅快速/辅助）

对于草图或简单辅助图的绘制，本地安装的 Mermaid 可能比手工绘制更快SVG. 本地渲染为静态 SVG检查并清理输出，然后在行内插入 SVG. 从未发货 Mermaid 运行时或 CDN 页面中的脚本。 For the **carrying** 之前/之后图，手工SVG wins - 自动布局漂移，破坏了使差异可读的并排对齐。

<a id="public-repositories-commit-under-pr-and-use-an-htmlpreview-link"></a>

### 公共存储库：在 `.pr/` 下提交并使用 htmlpreview 链接

因为页面是 ** 自包含的 **，GitHub 可以通过 `htmlpreview.github.io`（它从 HTML 中获取原始内容并以正确的内容类型 - 仅 `raw.githubusercontent.com` 不会，它返回 `text/plain`）来渲染。 将文件提交到临时 `.pr/` 目录下的 PR 分支，然后构建链接并将其粘贴到 PR 描述中：

```bash
# 提交 PR 分支上 .pr/ 下的 HTML（该目录是临时的，请参阅技巧）
git add .pr/design.html && git commit -m "docs(.pr): design doc" && git push <your-fork> <branch>
# 在链接中使用推送文档提交的完整 SHA：
git rev-parse HEAD
#   https://htmlpreview.github.io/?https://github.com/ <fork-owner>/<repo>/blob/<doc-commit-sha>/.pr/design.html
```

形状示例：
`https://htmlpreview.github.io/?https://github.com/FORK_OWNER/REPO/blob/DOC_COMMIT_SHA/.pr/design.html`

将 URL 指向 **PR 头存储库和包含文档 ** 的完整提交 SHA。 当 `.pr/` 被清理时，基于分支的链接可能会在合并后中断； 提交固定链接在清理之前继续引用文档。 当实质性更改影响设计时，刷新文档及其链接。

对于公共存储库，任何人都可以打开呈现的页面，而无需下载或本地服务器。 这适用于仅包含内联 CSS 和 SVG 的独立页面。

<a id="private-repositories-keep-the-preview-private"></a>

### 私有存储库：保持预览私有

`htmlpreview` 无法获取私有存储库内容。 请勿通过将设计文档发布到 GitHub Pages 或其他公共主机来解决此问题。 保持文档不含外部脚本和资源：打开本地文件不会使第三方活动内容变为私有。

- 将审阅者链接到完整文档提交 SHA 处的 GitHub blob，并要求他们在本地下载并打开独立的 HTML 文件； 或使用现有的工件服务，例如 htmlpreview.github.io。
- 如需本地浏览器预览，请直接打开 `.pr/design.html`。 如果浏览器需要 HTTP，则仅在环回上提供服务：
  ```bash
  python -m http.server 8000 --bind 127.0.0.1 --directory .pr
  # 打开 http://127.0.0.1:8000/design.html
  ```
- 仅当用户明确授权发布并且您确认为此存储库启用了私有页面访问控制时，才使用 GitHub 页面。
