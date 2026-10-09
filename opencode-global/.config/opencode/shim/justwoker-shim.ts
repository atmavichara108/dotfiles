#!/usr/bin/env bun
import { request as nodeHttpRequest } from "node:http";
import { request as nodeHttpsRequest } from "node:https";
import { Readable } from "node:stream";
import type { IncomingMessage } from "node:http";
/**
 * justwoker-shim — локальный HTTP-шим для провайдера `justwoker`.
 *
 * Зачем: upstream api.justwoker.icu регрессировал SSE — на stream:true он
 * отдаёт только message_start/message_delta/message_stop, без content_block_*
 * (то есть без текста). Без стрима тот же запрос работает. OpenCode (AI SDK)
 * всегда стримит, поэтому шим перехватывает стрим-запрос, форвардит его наверх
 * как non-stream и сам синтезирует корректный Anthropic SSE.
 *
 * Границы:
 *  - слушает только localhost;
 *  - auth-заголовки прокидывает как есть (x-api-key / authorization), сам их
 *    не хранит и не логирует;
 *  - тела запросов/ответов, промпты и секреты не логируются.
 *
 * Env: HOST (default 127.0.0.1), PORT (default 8787),
 *      UPSTREAM_BASE (default https://api.justwoker.icu/v1).
 */

const UPSTREAM_BASE = (process.env.UPSTREAM_BASE ?? "https://api.justwoker.icu/v1").replace(/\/+$/, "");
const HOST = process.env.HOST ?? "127.0.0.1";
const PORT = Number(process.env.PORT ?? 8787);

const REQ_HOP_BY_HOP = new Set([
  "host", "content-length", "connection", "keep-alive", "transfer-encoding",
  "upgrade", "proxy-authorization", "proxy-connection", "te", "trailer",
  "accept-encoding",
]);
const RES_HOP_BY_HOP = new Set([
  "content-length", "content-encoding", "transfer-encoding", "connection",
  "keep-alive", "upgrade", "trailer", "te",
]);

function upstreamUrl(reqUrl: string): string {
  const u = new URL(reqUrl);
  const path = u.pathname.replace(/^\/v1(?=\/|$)/, "");
  return UPSTREAM_BASE + path + u.search;
}

function buildUpstreamHeaders(req: Request, bodyLen: number): Headers {
  const h = new Headers();
  for (const [k, v] of req.headers) {
    if (REQ_HOP_BY_HOP.has(k.toLowerCase())) continue;
    h.set(k, v);
  }
  h.set("content-length", String(bodyLen));
  return h;
}

// Потолок времени апстрим-запроса. Держит AbortSignal; дефолтный Bun-овый
// socket-idle (300c) отключён через fetch-опцию `timeout: false` (доказано
// контрольным тестом: hold=340c → 200; см. ниже). 900c с запасом на полный
// контекст Opus.
const UPSTREAM_TIMEOUT_MS = Number(process.env.UPSTREAM_TIMEOUT_MS ?? 900_000);
const FORWARD_RETRIES = Number(process.env.FORWARD_RETRIES ?? 3);
const FORWARD_RETRY_MS = Number(process.env.FORWARD_RETRY_MS ?? 1500);
// Детектор висняка: если от upstream нет ни байта дольше HANG_MS — аборт
// попытки и ретрай форварда. Даёт дистрибьютору шанс перевыделить живой
// канал (симптом «висит 15 минут»). Клиента держат пинги.
const HANG_MS = Number(process.env.HANG_MS ?? 90_000);

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Плоская запись заголовков (Headers → Record) для node:http(s).request. */
function headersRecord(h: Headers): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of h) out[k] = v;
  return out;
}

type RawUpstream = {
  status: number;
  headers: Record<string, string | string[] | undefined>;
  stream: IncomingMessage;
};

/**
 * Свежее TCP+TLS-соединение на КАЖДЫЙ запрос (agent:false, keep-alive off).
 * Bun fetch-пул в долгоживущем процессе реюзает мёртвый сокет (Cloudflare
 * убивает idle-соединение), тело застревает в Send-Q и запрос висит до
 * потолка AbortSignal. node:https с agent:false регрессии не имеет
 * (proven: выживает 340c hold, тест T3).
 */
function openRaw(
  upstreamUrlStr: string,
  method: string,
  headers: Record<string, string>,
  body: string | undefined,
  signal: AbortSignal,
): Promise<RawUpstream> {
  const u = new URL(upstreamUrlStr);
  const isHttps = u.protocol === "https:";
  const reqFn = isHttps ? nodeHttpsRequest : nodeHttpRequest;
  return new Promise((resolve, reject) => {
    const options: any = {
      protocol: u.protocol,
      hostname: u.hostname,
      port: u.port || (isHttps ? 443 : 80),
      path: u.pathname + u.search,
      method,
      headers,
    };
    options.agent = false; // без пула: новое TCP-соединение на каждый запрос
    const r = reqFn(options, (res: IncomingMessage) => {
      resolve({ status: res.statusCode ?? 0, headers: res.headers, stream: res });
    });
    const onAbort = () => r.destroy(new Error("shim: aborted"));
    if (signal.aborted) onAbort();
    else signal.addEventListener("abort", onAbort, { once: true });
    r.on("error", reject);
    if (body !== undefined) r.write(body);
    r.end();
  });
}

/**
 * Свежее TCP+TLS-соединение на КАЖДЫЙ запрос (agent:false, keep-alive off).
 * Bun fetch-пул в долгоживущем процессе реюзает мёртвый сокет (Cloudflare
 * убивает idle-соединение), тело застревает в Send-Q и запрос висит до
 * потолка AbortSignal. node:https с agent:false регрессии не имеет
 * (proven: выживает 340c hold, тест T3).
 */
function openUpstream(req: Request, body: string | undefined, signal: AbortSignal): Promise<RawUpstream> {
  return openRaw(
    upstreamUrl(req.url),
    req.method,
    headersRecord(buildUpstreamHeaders(req, body ? Buffer.byteLength(body) : 0)),
    body,
    signal,
  );
}

/** Форвард апстрима через node:https с прозрачным ретраем 403/503. */
async function forward(req: Request, body: string, signal: AbortSignal): Promise<RawUpstream> {
  for (let attempt = 0; attempt <= FORWARD_RETRIES; attempt++) {
    const up = await openUpstream(req, body, signal);
    // Быстрые отказы балансировщика (CF rate-limit 403, New API «No available
    // channel» 503): прозрачный ретрай с паузой — OpenCode их не видит.
    if ((up.status === 403 || up.status === 503) && attempt < FORWARD_RETRIES) {
      console.log(`[shim] upstream ${up.status} retry ${attempt + 1}/${FORWARD_RETRIES}`);
      up.stream.destroy();
      await sleep(FORWARD_RETRY_MS * (attempt + 1));
      continue;
    }
    return up;
  }
  throw new Error("shim: forward retries exhausted");
}

/** Заголовки ответа апстрима без hop-by-hop. */
function filteredHeaders(rec: Record<string, string | string[] | undefined>): Headers {
  const h = new Headers();
  for (const [k, v] of Object.entries(rec)) {
    if (v === undefined) continue;
    if (RES_HOP_BY_HOP.has(k.toLowerCase())) continue;
    h.set(k, Array.isArray(v) ? v.join(", ") : v);
  }
  return h;
}

/** Полное чтение node-стрима в строку (для non-stream/facade). */
async function readAll(stream: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of stream) chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c));
  return Buffer.concat(chunks).toString("utf8");
}

/** Чистый ответ-ошибка JSON (не бросаем наружу, не валим процесс). */
function jsonError(status: number, message: string): Response {
  return new Response(
    JSON.stringify({ type: "error", error: { type: "upstream_error", message } }),
    { status, headers: { "content-type": "application/json" } },
  );
}

function sseEvent(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Синтез корректного Anthropic SSE из non-stream JSON-ответа. */
function buildSSE(json: any): string {
  const id = typeof json?.id === "string" ? json.id : "msg_shim_" + crypto.randomUUID();
  const model = typeof json?.model === "string" ? json.model : "unknown";
  const content: any[] = Array.isArray(json?.content) ? json.content : [];
  const usage = json?.usage ?? {};
  const inputTokens = Number.isFinite(usage.input_tokens) ? usage.input_tokens : 0;
  const outputTokens = Number.isFinite(usage.output_tokens) ? usage.output_tokens : 0;
  const stopReason = typeof json?.stop_reason === "string" ? json.stop_reason : "end_turn";
  const stopSequence = json?.stop_sequence ?? null;

  let out = "";
  out += sseEvent("message_start", {
    type: "message_start",
    message: {
      id, type: "message", role: "assistant", model, content: [],
      stop_reason: null, stop_sequence: null,
      usage: { input_tokens: inputTokens, output_tokens: 0 },
    },
  });

  content.forEach((block, index) => {
    const type = block?.type;
    if (type === "tool_use") {
      out += sseEvent("content_block_start", {
        type: "content_block_start", index,
        content_block: { type: "tool_use", id: block.id, name: block.name, input: {} },
      });
      out += sseEvent("content_block_delta", {
        type: "content_block_delta", index,
        delta: { type: "input_json_delta", partial_json: JSON.stringify(block.input ?? {}) },
      });
      out += sseEvent("content_block_stop", { type: "content_block_stop", index });
    } else if (type === "thinking") {
      out += sseEvent("content_block_start", {
        type: "content_block_start", index,
        content_block: { type: "thinking", thinking: "" },
      });
      out += sseEvent("content_block_delta", {
        type: "content_block_delta", index,
        delta: { type: "thinking_delta", thinking: block.thinking ?? "" },
      });
      out += sseEvent("content_block_stop", { type: "content_block_stop", index });
    } else {
      out += sseEvent("content_block_start", {
        type: "content_block_start", index,
        content_block: { type: "text", text: "" },
      });
      out += sseEvent("content_block_delta", {
        type: "content_block_delta", index,
        delta: { type: "text_delta", text: block?.text ?? "" },
      });
      out += sseEvent("content_block_stop", { type: "content_block_stop", index });
    }
  });

  out += sseEvent("message_delta", {
    type: "message_delta",
    delta: { stop_reason: stopReason, stop_sequence: stopSequence },
    usage: { output_tokens: outputTokens, input_tokens: inputTokens },
  });
  out += sseEvent("message_stop", { type: "message_stop" });
  return out;
}

/**
 * OpenAI-фасад: /v1/chat/completions → upstream /v1/messages (Anthropic-style).
 * Нужен, чтобы tools/model-bench (говорит по OpenAI-протоколу Bearer'ом) мог
 * бениТЬ justwoker, у которого OpenAI-путь закрыт Cloudflare, а рабочий только
 * anthropic-messages. Перевод односторонний: text-only ответ (tool_calls бенчер
 * не использует).
 */
function openaiToAnthropic(body: any): any {
  const msgs = Array.isArray(body?.messages) ? body.messages : [];
  const systemParts: string[] = [];
  const messages: any[] = [];
  for (const m of msgs) {
    const role = m?.role;
    const content =
      typeof m?.content === "string"
        ? m.content
        : Array.isArray(m?.content)
          ? m.content.map((p: any) => (typeof p === "string" ? p : p?.text ?? "")).join("")
          : "";
    if (role === "system") {
      if (content) systemParts.push(content);
    } else if (role === "assistant") {
      messages.push({ role: "assistant", content });
    } else {
      messages.push({ role: "user", content });
    }
  }
  const out: any = {
    model: body?.model,
    max_tokens: Number.isFinite(body?.max_tokens) ? body.max_tokens : 4096,
    messages,
  };
  if (systemParts.length) out.system = systemParts.join("\n");
  if (Number.isFinite(body?.temperature)) out.temperature = body.temperature;
  if (Number.isFinite(body?.top_p)) out.top_p = body.top_p;
  if (Array.isArray(body?.stop) && body.stop.length) out.stop_sequences = body.stop.slice(0, 4);
  else if (typeof body?.stop === "string" && body.stop) out.stop_sequences = [body.stop];
  return out;
}

function anthropicToOpenAI(json: any): any {
  const content: any[] = Array.isArray(json?.content) ? json.content : [];
  const text = content
    .filter((b) => b?.type === "text")
    .map((b) => b?.text ?? "")
    .join("");
  const stopReason = json?.stop_reason;
  const finish =
    stopReason === "max_tokens" ? "length"
    : stopReason === "refusal" ? "content_filter"
    : stopReason === "tool_use" ? "tool_calls"
    : "stop";
  const usage = json?.usage ?? {};
  const promptTokens = Number.isFinite(usage.input_tokens) ? usage.input_tokens : 0;
  const completionTokens = Number.isFinite(usage.output_tokens) ? usage.output_tokens : 0;
  return {
    id: (typeof json?.id === "string" ? json.id : "chatcmpl-" + crypto.randomUUID()).replace(/^msg_/, "chatcmpl-"),
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: json?.model ?? "unknown",
    choices: [
      {
        index: 0,
        message: { role: "assistant", content: text },
        finish_reason: finish,
      },
    ],
    usage: {
      prompt_tokens: promptTokens,
      completion_tokens: completionTokens,
      total_tokens: promptTokens + completionTokens,
    },
  };
}

function extractBearer(req: Request): string {
  const auth = req.headers.get("authorization") ?? "";
  const m = auth.match(/^Bearer\s+(.+)$/i);
  return m ? m[1] : "";
}

const server = Bun.serve({
  hostname: HOST,
  port: PORT,
  idleTimeout: 255,
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/health" || url.pathname === "/") {
      return new Response("ok", { status: 200 });
    }

    let raw = "";
    if (req.method !== "GET" && req.method !== "HEAD") {
      raw = await req.text();
    }

    let parsed: any = null;
    if (raw) {
      try { parsed = JSON.parse(raw); } catch { parsed = null; }
    }

    try {
      return await route(req, url, raw, parsed);
    } catch (err: any) {
      const name = err?.name ?? "";
      const isTimeout = name === "TimeoutError" || name === "AbortError";
      const status = isTimeout ? 504 : 502;
      console.log(`[shim] ${req.method} ${url.pathname} -> ${status} (${name || "error"}: ${err?.message ?? ""})`);
      return jsonError(status, `shim: ${isTimeout ? "upstream timeout" : "upstream error"}`);
    }
  },
});

async function route(req: Request, url: URL, raw: string, parsed: any): Promise<Response> {

    // ── OpenAI-фасад для бенчера: /v1/chat/completions → /v1 messages ──
    // Держим на non-stream-пути (бенчеру нужен целый JSON).
    if (url.pathname === "/v1/chat/completions" && req.method === "POST" && parsed) {
      const anthBody = openaiToAnthropic(parsed);
      const key = extractBearer(req) || req.headers.get("x-api-key") || "";
      const ac = new AbortController();
      const hardTimer = setTimeout(() => ac.abort(), UPSTREAM_TIMEOUT_MS);
      let up: RawUpstream;
      try {
        up = await openRaw(
          UPSTREAM_BASE + "/messages",
          "POST",
          { "content-type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": key },
          JSON.stringify(anthBody),
          ac.signal,
        );
      } catch {
        clearTimeout(hardTimer);
        return jsonError(502, "shim: upstream error (facade)");
      }
      if (up.status < 200 || up.status >= 300) {
        clearTimeout(hardTimer);
        up.stream.destroy();
        console.log(`[shim] POST /v1/chat/completions -> ${up.status} (upstream error, facade)`);
        return new Response(
          JSON.stringify({ error: { message: `shim: upstream ${up.status}`, type: "upstream_error" } }),
          { status: up.status || 502, headers: { "content-type": "application/json" } },
        );
      }
      let text = "";
      try {
        text = await readAll(up.stream);
      } catch {
        clearTimeout(hardTimer);
        return jsonError(502, "shim: upstream stream error (facade)");
      }
      clearTimeout(hardTimer);
      let j: any = null;
      try { j = JSON.parse(text); } catch { j = null; }
      if (!j) {
        return new Response(
          JSON.stringify({ error: { message: "shim: upstream non-JSON (facade)", type: "api_error" } }),
          { status: 502, headers: { "content-type": "application/json" } },
        );
      }
      console.log(`[shim] POST /v1/chat/completions -> 200 (OpenAI facade)`);
      return new Response(JSON.stringify(anthropicToOpenAI(j)), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }

    const wantsStream = parsed?.stream === true;

    // Non-stream запрос: форвардим как есть, тело ответа — потоком.
    if (!wantsStream) {
      const ac = new AbortController();
      let up: RawUpstream;
      try {
        up = await forward(req, raw, ac.signal);
      } catch {
        return jsonError(502, "shim: upstream error");
      }
      const hardTimer = setTimeout(() => ac.abort(), UPSTREAM_TIMEOUT_MS);
      up.stream.on("close", () => clearTimeout(hardTimer));
      console.log(`[shim] ${req.method} ${url.pathname} -> ${up.status} (passthrough)`);
      const bodyStream = Readable.toWeb(up.stream) as unknown as ReadableStream<Uint8Array>;
      return new Response(bodyStream, { status: up.status, headers: filteredHeaders(up.headers) });
    }

    // ── Гибридный passthrough (v3) ──
    // Форвардим наверх с stream:true и пробрасываем СЫРЫЕ SSE-байты:
    // peek-then-flush по маркеру `content_block` (мгновенный TTFB, живые
    // инкрементальные дельты), без парсинга/пересборки. Если стрим завершился
    // БЕЗ content_block (старая регрессия upstream) — fallback на non-stream
    // и синтез SSE (buildSSE). Нет чанков дольше HANG_MS → abort + ретрай
    // форварда; клиента держат пинги (crash-guard safeEnqueue/closed).
    const enc = new TextEncoder();
    let hb: ReturnType<typeof setInterval> | undefined;
    let closed = false;
    const stopHb = () => { if (hb) { clearInterval(hb); hb = undefined; } };

    // Fallback: повтор запроса как non-stream + синтез. Возвращает JSON|null.
    const synthNonStream = async (): Promise<any> => {
      const ac = new AbortController();
      const t = setTimeout(() => ac.abort(), UPSTREAM_TIMEOUT_MS);
      try {
        const up = await forward(req, JSON.stringify({ ...parsed, stream: false }), ac.signal);
        const text = await readAll(up.stream);
        if (up.status < 200 || up.status >= 300) return null;
        return JSON.parse(text);
      } catch {
        return null;
      } finally {
        clearTimeout(t);
      }
    };

    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        // Crash-guard: после cancel() клиента контроллер закрыт — enqueue/close
        // в него бросают TypeError и роняют процесс. Все записи через safeEnqueue.
        const safeEnqueue = (s: string | Uint8Array) => {
          if (closed) return;
          try { controller.enqueue(typeof s === "string" ? enc.encode(s) : s); }
          catch { closed = true; stopHb(); }
        };
        const safeClose = () => {
          if (closed) return;
          closed = true; stopHb();
          try { controller.close(); } catch {}
        };
        const fail = (msg: string) => {
          safeEnqueue(sseEvent("error", { type: "error", error: { type: "api_error", message: msg } }));
          safeClose();
        };
        // Клиента держат пинги (Bun idleTimeout default 10s иначе рвёт коннект).
        hb = setInterval(() => safeEnqueue(sseEvent("ping", { type: "ping" })), 8000);

        // true — ответ клиенту уже отдан (успех/ошибка); false — нужен fallback.
        const attemptStream = async (): Promise<boolean> => {
          for (let attempt = 0; attempt <= FORWARD_RETRIES; attempt++) {
            if (closed) return true;
            const ac = new AbortController();
            let reason = "";
            // Watchdog НЕ зависит от того, отклонит ли abort промис транспорта:
            // гоним forward/read через Promise.race с reject-таймерами.
            let hangTimer: ReturnType<typeof setTimeout> | undefined;
            let hardTimer: ReturnType<typeof setTimeout> | undefined;
            let rejectHang: (e: Error) => void = () => {};
            let rejectHard: (e: Error) => void = () => {};
            const hangP = new Promise<never>((_, rej) => { rejectHang = rej; });
            const hardP = new Promise<never>((_, rej) => { rejectHard = rej; });
            const armHang = () => {
              clearTimeout(hangTimer);
              hangTimer = setTimeout(() => { reason = "hang"; ac.abort(); rejectHang(new Error("hang")); }, HANG_MS);
            };
            const drop = () => { clearTimeout(hangTimer); clearTimeout(hardTimer); };
            let up: RawUpstream | undefined;
            armHang();
            hardTimer = setTimeout(() => { reason = "hard"; ac.abort(); rejectHard(new Error("hard")); }, UPSTREAM_TIMEOUT_MS);
            try {
              up = await Promise.race([forward(req, raw, ac.signal), hangP, hardP]);
              if (up.status < 200 || up.status >= 300) {
                drop();
                console.log(`[shim] ${req.method} ${url.pathname} -> upstream ${up.status} (SSE error event)`);
                up.stream.destroy();
                fail(`shim: upstream ${up.status}`);
                return true;
              }
              const reader = (Readable.toWeb(up.stream) as unknown as ReadableStream<Uint8Array>).getReader();
              const buffered: Uint8Array[] = [];
              const dec = new TextDecoder();
              let seen = "";
              let flushed = false;
              for (;;) {
                armHang();
                const step = await Promise.race([reader.read(), hangP, hardP]);
                if (closed) { await reader.cancel().catch(() => {}); drop(); return true; }
                if (step.done) break;
                const chunk = step.value;
                if (!flushed) {
                  buffered.push(chunk);
                  seen += dec.decode(chunk, { stream: true });
                  if (seen.includes("content_block")) {
                    stopHb();
                    for (const c of buffered) safeEnqueue(c);
                    buffered.length = 0;
                    flushed = true;
                  }
                } else {
                  safeEnqueue(chunk);
                }
              }
              drop();
              if (closed) return true;
              if (flushed) {
                console.log(`[shim] ${req.method} ${url.pathname} -> 200 (live SSE passthrough)`);
                safeClose();
                return true;
              }
              // Стрим кончился без content_block — регрессия: fallback на non-stream.
              console.log(`[shim] ${req.method} ${url.pathname} -> upstream stream had no content_block (fallback to non-stream)`);
              return false;
            } catch (err: any) {
              drop();
              if (up) up.stream.destroy();
              if (closed) return true;
              if (reason === "hang" && attempt < FORWARD_RETRIES) {
                console.log(`[shim] upstream hang >${HANG_MS}ms, retry ${attempt + 1}/${FORWARD_RETRIES}`);
                await sleep(FORWARD_RETRY_MS * (attempt + 1));
                continue;
              }
              fail(reason === "hard" ? "shim: upstream timeout" : "shim: upstream hang");
              return true;
            }
          }
          // Попытки исчерпаны на hang.
          fail("shim: upstream hang");
          return true;
        };

        (async () => {
          try {
            if (await attemptStream()) return;
            if (closed) return;
            const json = await synthNonStream();
            if (closed) return;
            if (!json) {
              console.log(`[shim] ${req.method} ${url.pathname} -> fallback non-stream non-JSON (SSE error event)`);
              fail("shim: upstream returned non-JSON");
              return;
            }
            const blocks = Array.isArray(json?.content) ? json.content.length : 0;
            console.log(`[shim] ${req.method} ${url.pathname} -> 200 (synthesized SSE, blocks=${blocks})`);
            safeEnqueue(buildSSE(json));
            safeClose();
          } catch (err: any) {
            if (closed) return;
            console.log(`[shim] ${req.method} ${url.pathname} -> ${err?.name ?? "error"} (SSE error event)`);
            fail(`shim: ${err?.name ?? "upstream error"}`);
          }
        })();
      },
      cancel() { closed = true; stopHb(); },
    });
    console.log(`[shim] ${req.method} ${url.pathname} -> 200 (stream open, keep-alive pings)`);
    return new Response(stream, {
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
        "connection": "keep-alive",
      },
    });
}

console.log(`[shim] justwoker-shim listening on http://${server.hostname}:${server.port} -> ${UPSTREAM_BASE}`);