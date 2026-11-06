// Минимальный репро: node:https agent:false, big body (796KB), три варианта записи.
import { request as nodeHttpsRequest } from "node:https";
import { readFileSync } from "node:fs";

const KEY = JSON.parse(readFileSync("/home/rudra/.local/share/opencode/auth.json", "utf8")).justwoker.key;
const BODY = readFileSync("/tmp/opencode/jw/big.json", "utf8");
const LEN = Buffer.byteLength(BODY);
console.log(`body=${LEN}B`);

function attempt(name, writeFn) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const r = nodeHttpsRequest({
      protocol: "https:", hostname: "api.justwoker.icu", port: 443, path: "/v1/messages",
      method: "POST",
      headers: { "content-type": "application/json", "content-length": String(LEN), "x-api-key": KEY, "anthropic-version": "2023-06-01" },
      agent: false,
    }, (res) => {
      let n = 0;
      res.on("data", (c) => { n += c.length; });
      res.on("end", () => resolve(`${name}: status=${res.statusCode} bytes=${n} t=${Date.now()-t0}ms`));
      res.on("error", (e) => resolve(`${name}: res-error ${e.message} t=${Date.now()-t0}ms`));
    });
    r.on("error", (e) => resolve(`${name}: req-error ${e.message} t=${Date.now()-t0}ms`));
    writeFn(r);
    setTimeout(() => { r.destroy(); resolve(`${name}: HANG t>=${Date.now()-t0}ms`); }, 30000);
  });
}

// Вариант 1: как в шиме — write(string) + end()
const v1 = await attempt("write+end", (r) => { r.write(BODY); r.end(); });
console.log(v1);
if (v1.includes("HANG") || v1.includes("error")) {
  // Вариант 2: end(body) одной операцией
  const v2 = await attempt("end(body)", (r) => { r.end(BODY); });
  console.log(v2);
  // Вариант 3: чанки по 64KB с дрейном
  const v3 = await attempt("chunks+drain", (r) => {
    const CHUNK = 64 * 1024;
    let off = 0;
    const writeNext = () => {
      while (off < LEN) {
        const end = Math.min(off + CHUNK, LEN);
        const ok = r.write(BODY.slice(off, end));
        off = end;
        if (!ok) { r.once("drain", writeNext); return; }
      }
      r.end();
    };
    writeNext();
  });
  console.log(v3);
}
