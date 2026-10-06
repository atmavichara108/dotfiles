#!/usr/bin/env node
// Maya-lint v2 — детерминированный сканер без LLM (sustainability-filter: zero-LLM-in-loop)
// Спека: docs/specs/maya-lint-v2 (dotfiles). Режимы: report (default) / --gate.
// Словарь: dictionary.json рядом, фразы-only, правит только librarian.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { execFileSync } from "node:child_process";

const HERE = dirname(fileURLToPath(import.meta.url));
const dict = JSON.parse(readFileSync(join(HERE, "dictionary.json"), "utf8"));
const args = process.argv.slice(2);
const gate = args.includes("--gate");
const rest = args.filter((a) => a !== "--gate");

let documents = []; // {label, text}
for (const target of rest) {
  if (target.startsWith("git:")) {
    // git:<repo> — скан истории коммитов (subject+body) последних 200
    const repo = target.slice(4);
    const log = execFileSync("git", ["-C", repo, "log", "--color=never", "-200", "--pretty=format:%H%x09%s%n%b"], { encoding: "utf8" });
    for (const block of log.split("\n\n")) documents.push({ label: `${repo}::git-log`, text: block });
  } else {
    const p = resolve(target);
    documents.push({ label: p, text: readFileSync(p, "utf8") });
  }
}

const whitelist = dict.whitelist || [];
const hits = [];
for (const doc of documents) {
  for (const term of dict.terms) {
    // phrase-only: регистронезависимый поиск составного терма
    const re = new RegExp(term.phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    for (const m of doc.text.matchAll(re)) {
      if (whitelist.some((w) => w.path === doc.label && term.phrase === w.phrase)) continue;
      hits.push({ document: doc.label, phrase: term.phrase, external: term.external });
    }
  }
}

if (hits.length === 0) {
  console.log(`maya-lint: PASS — 0 hits, ${documents.length} документы, словарь v${dict.version} (фразы-only)`);
  process.exit(0);
}
console.log("maya-lint:", gate ? "GATE-FAIL" : "REPORT", `— ${hits.length} hits, ${documents.length} документы`);
for (const h of hits.slice(0, 40)) console.log(`  ${gate ? "✗" : "•"} [${h.phrase} → ${h.external}] ${h.document}`);
if (hits.length > 40) console.log(`  … +${hits.length - 40}`);
process.exit(gate ? 1 : 0);
