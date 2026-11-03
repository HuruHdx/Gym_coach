# 给 Cursor 用的提示词

> 直接复制到 Cursor 的对话框里。第一条用来改存量，第二条用来写新页面，
> 第三条用来体检。规则文件已经把硬规则常驻了，这些提示词是"任务指令"。

---

## ① 把现有页面接到规范上（改存量）

```
读 gym-ui/DESIGN.md 和 gym-ui/components.css，理解规范。

然后重构 src/pages/Today.tsx（以及它引用的样式文件），把它接到规范上。要求：

1. 先只做"盘点"，不改代码：列出这个文件里所有裸色值、裸字号、裸圆角、裸间距，
   以及所有不满足 DESIGN.md 第 9/10 条的写法，做成表格：位置 / 现状 / 应改成什么变量
2. 等我确认后再动手
3. 改动范围只限样式，不改结构和业务逻辑
4. 每改完一个文件就停下来，告诉我改了什么、还有什么没标准化、为什么
5. 拿不准的地方问我，不要自己发明新的颜色或字号
```

---

## ② 新建页面（按规范）

```
按 gym-ui/DESIGN.md 第 7 节的标准页结构，新建 <页面名> 页面。

约束：
- 只用 gym-ui/components.css 里已有的类；实在缺的先说明缺什么、为什么现有类组合不出来，
  再提议新增，不要直接造一套平行组件
- 所有颜色/字号/圆角/间距走 tokens.css 变量
- 数据用假数据，但要有真实密度（具体的数字和日期，不要"示例文本"）
- 移动端优先，按 DESIGN.md 第 5 节的基线检查
- 完成后按 DESIGN.md 第 10 节逐条自查，每条给出结论（通过 / 不通过 + 原因）
```

---

## ③ 体检整个项目（不改代码，只出清单）

```
扫描 src 下所有 .css / .tsx / .scss 文件，对照 gym-ui/DESIGN.md 第 9、10 节，
找出所有违规处，输出成表格：

文件:行号 | 违反哪一条 | 现状代码 | 建议改法

不要直接修改任何文件，先给我完整清单。按"影响面"排序，
影响最大的（比如硬编码主色、缺 16px 输入字号）排前面。
```

---

## ④ 单点修复：深色模式看不清

```
深色主题下的小字看不清。按 gym-ui/DESIGN.md 第 1 节处理：

1. 用 WCAG 公式算出 [data-theme="dark"] 里 --text-1/--text-2/--text-3
   分别对 --bg 和 --surface 的对比度，列出来
2. 凡是低于 4.5 的，给出满足 4.5–6 区间的新色值（不要一味提亮到刺眼）
3. 检查有没有用 opacity 压暗文字的地方（opacity: .5/.6 之类），
   改成显式的颜色变量——opacity 在深底上不可控
4. 改完再算一遍对比度确认
```

---

## ⑤ 迁移主题色

```
把主题从淡紫换成 <目标色>，按 gym-ui/DESIGN.md 第 1 节的颜色角色表执行：

1. 只改 tokens.css 里 [data-theme="lavender"] 那一块，不碰组件
2. 必须同时给出四个值：--accent（填充）、--accent-text（文字，要比 accent 深）、
   --accent-ink（压在填充上的字）、--accent-soft（极浅底）
3. 算给我看：--accent-text 对 --bg 的对比度必须 ≥ 4.5；
   --accent-ink 对 --accent 的对比度必须 ≥ 4.5
4. 如果这个颜色当文字注定不合格（比如亮黄、亮青），明确指出，
   并说明只能当填充色使用
```

---

## 接进项目（一次性）

1. 把 `gym-ui/` 整个目录放到仓库根目录
2. 把 `gym-ui/.cursor/rules/gym-ui.mdc` 移到**仓库根**的 `.cursor/rules/` 下
   （Cursor 只认根目录的 `.cursor/rules`）
3. 入口文件里按顺序引入：

```ts
import "./gym-ui/tokens.css";
import "./gym-ui/base.css";
import "./gym-ui/components.css";
```

4. 在 `index.html` 的 `<html>` 上设默认主题：

```html
<html lang="zh-CN" data-theme="lavender">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
<meta name="theme-color" content="#f5f4fa">
```

5. 切主题只需要 `document.documentElement.dataset.theme = "dark"`
