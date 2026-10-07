#!/usr/bin/env bun
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

function filterResponseHeaders(src: Headers): Headers {
  const h = new Headers();
  for (const [k, v] of src) {
    if (RES_HOP_BY_HOP.has(k.toLowerCase())) continue;
    h.set(k, v);
  }
  return h;
}

// Потолок времени апстрим-запроса. Держит AbortSignal; дефолтный Bun-овый
// socket-idle (300c) отключён через fetch-опцию `timeout: false` (доказано
// контрольным тестом: hold=340c → 200; см. ниже). 900c с запасом на полный
// контекст Opus.
const UPSTREAM_TIMEOUT_MS = Number(process.env.UPSTREAM_TIMEOUT_MS ?? 900_000);
const FORWARD_RETRIES = Number(process.env.FORWARD_RETRIES ?? 3);
const FORWARD_RETRY_MS = Number(process.env.FORWARD_RETRY_MS ?? 1500);

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function forward(req: Request, body: string): Promise<Response> {
  const headers = buildUpstreamHeaders(req, Buffer.byteLength(body));
  const noBody = req.method === "GET" || req.method === "HEAD";
  const url = upstreamUrl(req.url);
  let res: Response | null = null;
  for (let attempt = 0; attempt <= FORWARD_RETRIES; attempt++) {
    res = await fetch(url, {
      method: req.method,
      headers,
      body: noBody ? undefined : body,
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      // Bun fetch НЕ знает опций headersTimeout/requestTimeout (они серверные,
      // Bun.serve/node:http). Клиентский socket-idle в Bun = 300c
      // (BUN_CONFIG_HTTP_IDLE_TIMEOUT) и рвёт долгий non-stream с TimeoutError.
      // Единственный рабочий escape-hatch — `timeout: false` (issue #16682).
      // Контрольный тест (hold=340c): fetch default → TimeoutError@300.0c;
      // fetch timeout:false → 200@340.1c. Потолок держит AbortSignal выше.
      timeout: false,
    } as RequestInit);
    // Быстрые отказы балансировщика up stream (CF rate-limit 403 ~0.5c,
    // New API «No available channel, distributor» 503): прозрачный ретрай
    // с паузой — OpenCode не должен их видеть.
    if ((res.status === 403 || res.status === 503) && attempt < FORWARD_RETRIES) {
      console.log(`[shim] upstream ${res.status} retry ${attempt + 1}/${FORWARD_RETRIES}`);
      await res.body?.cancel().catch(() => {});
      await sleep(FORWARD_RETRY_MS * (attempt + 1));
      continue;
    }
    return res;
  }
  return res;
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
    if (url.pathname === "/v1/chat/completions" && req.method === "POST" && parsed) {
      const anthBody = openaiToAnthropic(parsed);
      const key = extractBearer(req) || req.headers.get("x-api-key") || "";
      const res = await fetch(UPSTREAM_BASE + "/messages", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "anthropic-version": "2023-06-01",
          "x-api-key": key,
        },
        body: JSON.stringify(anthBody),
      });
      if (!res.ok) {
        console.log(`[shim] POST /v1/chat/completions -> ${res.status} (upstream error, facade)`);
        return new Response(
          JSON.stringify({ error: { message: `shim: upstream ${res.status}`, type: "upstream_error" } }),
          { status: res.status, headers: { "content-type": "application/json" } },
        );
      }
      const j = await res.json().catch(() => null);
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

    if (!wantsStream) {
      const res = await forward(req, raw);
      console.log(`[shim] ${req.method} ${url.pathname} -> ${res.status} (passthrough)`);
      return new Response(res.body, { status: res.status, headers: filterResponseHeaders(res.headers) });
    }

    // Стрим запрошен: форвардим наверх как non-stream.
    // ВАЖНО: отвечаем 200 СРАЗУ и держим соединение стандартными пингами
    // Anthropic SSE (`ping`), пока апстрим думает. Иначе Bun idleTimeout
    // (default 10s) рвёт "пустой" коннект, и OpenCode получает ECONNRESET
    // на любых генерациях длиннее ~10 секунд.
    const jsonBody = JSON.stringify({ ...parsed, stream: false });
    const enc = new TextEncoder();
    const upstream = forward(req, jsonBody);
    let hb: ReturnType<typeof setInterval> | undefined;
    // Crash-guard: после cancel() клиента контроллер закрыт — enqueue/close
    // в него бросают TypeError "Controller is already closed" и роняют
    // процесс (ConnectionRefused до Restart=always). Все записи — через
    // safeEnqueue с флагом closed.
    let closed = false;
    const stopHb = () => { if (hb) { clearInterval(hb); hb = undefined; } };
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const safeEnqueue = (s: string) => {
          if (closed) return;
          try { controller.enqueue(enc.encode(s)); } catch { closed = true; stopHb(); }
        };
        const safeClose = () => {
          if (closed) return;
          closed = true; stopHb();
          try { controller.close(); } catch {}
        };
        hb = setInterval(() => safeEnqueue(sseEvent("ping", { type: "ping" })), 8000);
        upstream
          .then(async (res) => {
            if (closed) return;
            stopHb();
            if (!res.ok) {
              console.log(`[shim] ${req.method} ${url.pathname} -> upstream ${res.status} (SSE error event)`);
              safeEnqueue(sseEvent("error", {
                type: "error",
                error: { type: "api_error", message: `shim: upstream ${res.status}` },
              }));
              safeClose();
              return;
            }
            const json = await res.json().catch(() => null);
            if (closed) return;
            if (!json) {
              console.log(`[shim] ${req.method} ${url.pathname} -> upstream non-JSON (SSE error event)`);
              safeEnqueue(sseEvent("error", {
                type: "error",
                error: { type: "api_error", message: "shim: upstream returned non-JSON" },
              }));
              safeClose();
              return;
            }
            const blocks = Array.isArray(json?.content) ? json.content.length : 0;
            console.log(`[shim] ${req.method} ${url.pathname} -> 200 (synthesized SSE, blocks=${blocks})`);
            safeEnqueue(buildSSE(json));
            safeClose();
          })
          .catch((err: any) => {
            if (closed) return;
            console.log(`[shim] ${req.method} ${url.pathname} -> ${err?.name ?? "error"} (SSE error event)`);
            safeEnqueue(sseEvent("error", {
              type: "error",
              error: { type: "api_error", message: `shim: ${err?.name ?? "upstream error"}` },
            }));
            safeClose();
          });
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