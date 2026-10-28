#!/usr/bin/env node
/**
 * 端点审计 — 协调手写的 Agent Server HTTP 反对
 * 在双向中都锁定 Agent Server OpenAPI 的规格。
 *
 *   - 仅客户端：服务器不存在手写 Agent Server 调用；
 *   - 仅服务器：服务器公开一个没有手写调用的操作。
 *
 * 明确排除另一个后端拥有的调用，例如 CloudClient
 * 在endpoint-audit.config.json中。 检查生成的传输层覆盖范围
 * 分别通过检查：智能体-服务器-API。
 *
 * 门控违规时退出代码不为零（请参阅config.gate）。
 */
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

import { loadPinnedAgentServerOpenApi } from './agent-server-openapi.mjs';

const ROOT = process.cwd();
const cfg = JSON.parse(fs.readFileSync(path.join(ROOT, 'endpoint-audit.config.json'), 'utf8'));

const VERBS = ['get', 'post', 'put', 'patch', 'delete'];

// "/api/x/${id}" 或 "/api/x/{name}" -> "/api/x/{}"，剥离查询 + 尾部斜杠
const norm = (verb, p) =>
  `${verb.toUpperCase()} ${
    p
      .split('?')[0]
      .replace(/\$?\{[^{}]*\}/g, '{}')
      .replace(/\/+$/, '') || '/'
  }`;

// ---------------------------------------------------------------------------
// 1. Agent Server 合同
// ---------------------------------------------------------------------------
async function loadSpec(spec) {
  if (spec.source === 'pinned-agent-server-release') {
    const result = await loadPinnedAgentServerOpenApi({
      repositoryRoot: ROOT,
      explicitSchemaPath: process.env.AGENT_SERVER_OPENAPI_PATH,
    });
    return { doc: result.schema, source: result.source };
  }
  if (spec.url) {
    try {
      const res = await fetch(spec.url, { signal: AbortSignal.timeout(8000) });
      if (res.ok) return { doc: await res.json(), source: spec.url };
      console.warn(`  ! ${spec.name}: ${spec.url} -> HTTP ${res.status}, falling back to file`);
    } catch (e) {
      console.warn(
        `  ! ${spec.name}: ${spec.url} unreachable (${e.message}), falling back to file`
      );
    }
  }
  if (spec.file && fs.existsSync(path.join(ROOT, spec.file)))
    return {
      doc: JSON.parse(fs.readFileSync(path.join(ROOT, spec.file), 'utf8')),
      source: path.join(ROOT, spec.file),
    };
  throw new Error(`spec "${spec.name}": no reachable url and no fallback file`);
}

const specToSet = (doc) => {
  const set = new Set(); // 标准化“VERB/path"
  for (const [p, methods] of Object.entries(doc.paths ?? {}))
    for (const verb of Object.keys(methods)) if (VERBS.includes(verb)) set.add(norm(verb, p));
  return set;
};

const contract = new Set();
const contractSources = [];
for (const spec of cfg.specs) {
  const { doc, source } = await loadSpec(spec);
  contractSources.push(source);
  for (const endpoint of specToSet(doc)) contract.add(endpoint);
}

// ---------------------------------------------------------------------------
// 2. 手写Agent Server客户端界面
// ---------------------------------------------------------------------------
function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === '__tests__' || e.name === 'node_modules') continue;
      out.push(...walk(full));
    } else if (e.name.endsWith('.ts')) out.push(full);
  }
  return out;
}

const excludedClientFiles = new Set(
  (cfg.excludeClientFiles ?? []).map((file) => path.normalize(file))
);

function pathFromExpression(expression) {
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
    return expression.text;
  }
  if (ts.isTemplateExpression(expression)) {
    return (
      expression.head.text +
      expression.templateSpans.map((span) => `{}` + span.literal.text).join('')
    );
  }
}

function objectProperty(object, name) {
  return object.properties.find(
    (property) =>
      ts.isPropertyAssignment(property) &&
      ((ts.isIdentifier(property.name) && property.name.text === name) ||
        (ts.isStringLiteral(property.name) && property.name.text === name))
  );
}

function extractEndpoints(file) {
  const source = ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS
  );
  const endpoints = [];

  function visit(node) {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
      const method = node.expression.name.text.toLowerCase();
      let verb;
      let endpointPath;

      if (VERBS.includes(method)) {
        verb = method;
        endpointPath = node.arguments[0] && pathFromExpression(node.arguments[0]);
      } else if (
        method === 'request' &&
        node.arguments[0] &&
        ts.isObjectLiteralExpression(node.arguments[0])
      ) {
        const options = node.arguments[0];
        const methodProperty = objectProperty(options, 'method');
        const urlProperty = objectProperty(options, 'url');
        if (methodProperty && urlProperty) {
          verb = pathFromExpression(methodProperty.initializer)?.toLowerCase();
          endpointPath = pathFromExpression(urlProperty.initializer);
        }
      }

      if (
        verb &&
        VERBS.includes(verb) &&
        endpointPath &&
        /^(?:\/$|\/(?:api|server_info|alive|health|ready)(?:\/|$))/.test(endpointPath)
      ) {
        endpoints.push(norm(verb, endpointPath));
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(source);
  return endpoints;
}

const client = new Set();
for (const glob of cfg.clientGlobs) {
  for (const file of walk(path.join(ROOT, glob))) {
    if (excludedClientFiles.has(path.normalize(path.relative(ROOT, file)))) continue;
    for (const endpoint of extractEndpoints(file)) client.add(endpoint);
  }
}

// ---------------------------------------------------------------------------
// 3. 差异
// ---------------------------------------------------------------------------
const sorted = (it) => [...it].sort();
const ignoredApi = (k) => (cfg.ignoreServerOnly ?? []).some((pre) => k.includes(pre));
const flattenExceptions = (groups) =>
  (groups ?? []).flatMap(({ endpoints, ...metadata }) =>
    endpoints.map((endpoint) => ({ endpoint, ...metadata }))
  );

const allowedClientOnly = flattenExceptions(cfg.allowClientOnly);
const explicitlyCoveredServerOperations = flattenExceptions(cfg.coveredServerOperations);
const allowedClientOnlySet = new Set(allowedClientOnly.map(({ endpoint }) => endpoint));
const coveredServerSet = new Set(explicitlyCoveredServerOperations.map(({ endpoint }) => endpoint));

const clientOnly = sorted(
  [...client].filter((k) => !contract.has(k) && !allowedClientOnlySet.has(k))
);
const serverOnly = sorted(
  [...contract].filter((k) => !client.has(k) && !coveredServerSet.has(k) && !ignoredApi(k))
);

// ---------------------------------------------------------------------------
// 4. 报告
// ---------------------------------------------------------------------------
const section = (title, items) => {
  console.log(`\n${title} (${items.length})`);
  for (const k of items) console.log(`  ${k}`);
};
console.log(
  `\n=== Endpoint audit — agent-server=${contract.size} audited-client=${client.size} ===`
);
section('⚠️ CLIENT-ONLY — handwritten call absent from agent-server', clientOnly);
section('⚠️ SERVER-ONLY — agent-server operation has no handwritten call', serverOnly);

fs.mkdirSync(path.join(ROOT, '.audit'), { recursive: true });
const gateConfig = cfg.gate ?? {};
fs.writeFileSync(
  path.join(ROOT, '.audit/endpoint-audit.json'),
  JSON.stringify(
    {
      agentServer: contract.size,
      client: client.size,
      contractSources,
      excludedClientFiles: sorted(excludedClientFiles),
      clientOnly,
      serverOnly,
      allowedClientOnly,
      explicitlyCoveredServerOperations,
      // 向后兼容现有工件使用者的字段名称。
      mismatch: clientOnly,
      missingApi: serverOnly,
      gate: {
        clientOnly: gateConfig.mismatch !== false,
        serverOnly: Boolean(gateConfig.missingApi),
      },
    },
    null,
    2
  )
);

// ---------------------------------------------------------------------------
// 5. 门
// ---------------------------------------------------------------------------
const violations = [];
if (gateConfig.mismatch !== false && clientOnly.length)
  violations.push(`${clientOnly.length} client-only`);
if (gateConfig.missingApi && serverOnly.length) violations.push(`${serverOnly.length} server-only`);

if (violations.length) {
  console.error(`\n❌ endpoint audit failed: ${violations.join(', ')}`);
  process.exit(1);
}
console.log('\n✅ endpoint audit passed');
