// tsc 运行后，将非 TS 资源 (.JSON) 从 src/ 复制到 dist/。 即使使用 resolveJsonModule，tsc 也不会发出导入的 JSON 文件； 如果没有此步骤，`import x from './acp-providers.json'` 将在编译时解析，但在已发布的包中运行时失败。
//

import { copyFile, mkdir, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(ROOT, 'src');
const DIST = path.join(ROOT, 'dist');
const EXTENSIONS = new Set(['.json']);

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walk(full)));
    } else if (EXTENSIONS.has(path.extname(entry.name))) {
      files.push(full);
    }
  }
  return files;
}

const sources = await walk(SRC);
for (const src of sources) {
  const rel = path.relative(SRC, src);
  const dest = path.join(DIST, rel);
  await mkdir(path.dirname(dest), { recursive: true });
  await copyFile(src, dest);
}

if (sources.length > 0) {
  console.log(`copy-json-assets: copied ${sources.length} file(s) to dist/`);
}
