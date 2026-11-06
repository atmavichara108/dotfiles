// Уточнение границы бага: keepAlive:false agent vs curl h1.1 vs Bun fetch.
import { request as nodeHttpsRequest, Agent } from "node:https";
import { readFileSync } from "node:fs";
import { execFile } from "node:child_process";

const KEY = JSON.parse(readFileSync("/home/rudra/.local/share/opencode/auth.json", "utf8")).justwoker.key;
const BODY = readFileSync("/tmp/opencode/jw/big.json", "utf8");
const LEN = Buffer.byteLength(BODY);

function attempt(name, makeReq) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const r = makeReq((res) => {
      let n = 0;
      res.on("data", (c) => { n += c.length; });
      res.on("end", () => resolve(`${name}: status=${res.statusCode} bytes=${n} t=${Date.now()-t0}ms`));
      res.on("error", (e) => resolve(`${name}: res-error ${e.message} t=${Date.now()-t0}ms`));
    });
    r.on("error", (e) => resolve(`${name}: req-error ${e.message} t=${Date.now()-t0}ms`));
    r.write(BODY); r.end();
    setTimeout(() => { r.destroy(); resolve(`${name}: HANG t>=${Date.now()-t0}ms`); }, 30000);
  });
}

// v4: keepAlive:false Agent (пул на один запрос, сокет не реюзается)
console.log(await attempt("keepAlive-false", (cb) => nodeHttpsRequest({
  protocol: "https:", hostname: "api.justwoker.icu", port: 443, path: "/v1/messages", method: "POST",
  headers: { "content-type": "application/json", "content-length": String(LEN), "x-api-key": KEY, "anthropic-version": "2023-06-01" },
  agent: new Agent({ keepAlive: false, maxSockets: 1 }),
}, cb)));

// v5: curl --http1.1 (контроль: работает ли HTTP/1.1 через Cloudflare с большим телом)
await new Promise((resolve) => {
  const t0 = Date.now();
  execFile("curl", ["-s", "-o", "/dev/null", "-w", "%{http_code} %{time_total}s http=%{http_version}\n",
    "--max-time", "30", "--http1.1", "-X", "POST", "https://api.justwoker.icu/v1/messages",
    "-H", "content-type: application/json", "-H", "x-api-key: " + KEY, "-H", "anthropic-version: 2023-06-01",
    "--data-binary", "@/tmp/opencode/jw/big.json"],
    { env: { ...process.env, PATH: process.env.PATH } },
    (err, stdout) => { console.log(`curl-h1.1: ${err ? "ERR " + err.message : stdout.trim()} t=${Date.now()-t0}ms`); resolve(); });
});

// v6: Bun fetch напрямую (контроль)
try {
  const t0 = Date.now();
  const res = await fetch("https://api.justwoker.icu/v1/messages", {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": KEY, "anthropic-version": "2023-06-01" },
    body: BODY, signal: AbortSignal.timeout(30000),
  });
  const text = await res.text();
  console.log(`bun-fetch: status=${res.statusCode ?? res.status} bytes=${text.length} t=${Date.now()-t0}ms`);
} catch (e) {
  console.log(`bun-fetch: ERR ${e.name} ${e.message}`);
}
