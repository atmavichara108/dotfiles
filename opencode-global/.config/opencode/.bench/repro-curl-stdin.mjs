// Тест: пишется ли большое тело в stdin curl-ребёнка через Bun + принимает ли upstream.
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";

const KEY = JSON.parse(readFileSync("/home/rudra/.local/share/opencode/auth.json", "utf8")).justwoker.key;
const BODY = readFileSync("/tmp/opencode/jw/big.json", "utf8");
const LEN = Buffer.byteLength(BODY);
console.log(`body=${LEN}B`);

const t0 = Date.now();
const child = spawn("curl", [
  "-sS", "-N", "--http1.1", "-i", "-X", "POST",
  "-H", "Expect:",
  "-H", "content-type: application/json",
  "-H", "x-api-key: " + KEY,
  "-H", "anthropic-version: 2023-06-01",
  "--data-binary", "@-",
  "--max-time", "60",
  "https://api.justwoker.icu/v1/messages",
], { stdio: ["pipe", "pipe", "pipe"] });

let out = "";
let err = "";
child.stdout.on("data", (c) => { out += c; });
child.stderr.on("data", (c) => { err += c; });
child.on("close", (code) => {
  const sep = out.indexOf("\r\n\r\n");
  const head = sep >= 0 ? out.slice(0, sep) : out.slice(0, 300);
  const body = sep >= 0 ? out.slice(sep + 4) : "";
  console.log(`exit=${code} t=${Date.now()-t0}ms`);
  console.log(`--- headers ---\n${head}`);
  console.log(`--- body len=${body.length} ---\n${body.slice(0, 200)}`);
  if (err) console.log(`--- stderr ---\n${err.slice(0, 500)}`);
});

// Пишем тело в stdin одним куском (как в шиме)
child.stdin.on("error", () => {});
child.stdin.write(BODY);
child.stdin.end();
