/**
 * promptfoo 会把 vars 顶层的数组做笛卡尔展开，长对话 turns 必须嵌进对象。
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const file = path.join(root, "cases-long.yaml");
const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);

if (lines.some((l) => l.includes("thread:") && l.trim() === "thread:")) {
  console.log("already nested");
  process.exit(0);
}

const out = [];
let i = 0;
let rewritten = 0;
while (i < lines.length) {
  const line = lines[i];
  const m = /^( {4})turns:\s*$/.exec(line);
  if (!m) {
    out.push(line);
    i += 1;
    continue;
  }
  const indent = m[1];
  out.push(`${indent}thread:`);
  out.push(`${indent}  turns:`);
  i += 1;
  while (i < lines.length) {
    const body = lines[i];
    // turns 子项是更深一层缩进（至少 6 空格），直到回到 vars 同级字段或 assert
    if (/^( {6,})\S/.test(body) || /^( {6,})$/.test(body)) {
      out.push(`  ${body}`);
      i += 1;
      continue;
    }
    break;
  }
  rewritten += 1;
}

if (!rewritten) {
  console.error("no turns blocks rewritten — abort");
  process.exit(1);
}

fs.writeFileSync(file, out.join("\n"));
console.log(`rewrote ${rewritten} turns blocks →`, file);
