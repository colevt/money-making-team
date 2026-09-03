#!/usr/bin/env node
/**
 * Tail ledger/events.jsonl and POST new lines to the Lovable ingest function.
 * Usage: node tools/ingest.mjs
 */
import { readFileSync, writeFileSync, existsSync, watchFile } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
loadEnv(join(root, ".env"));

const ledgerPath = resolve(process.env.LEDGER_PATH || join(root, "ledger", "events.jsonl"));
const offsetPath = join(root, "ledger", ".ingest-offset");
const url = process.env.LOVABLE_INGEST_URL;
const token = process.env.LOVABLE_INGEST_TOKEN;

if (!url || !token || token.startsWith("replace-")) {
  console.error("Set LOVABLE_INGEST_URL and LOVABLE_INGEST_TOKEN in .env");
  process.exit(1);
}

let sending = false;
await flush();
watchFile(ledgerPath, { interval: 800 }, () => {
  flush().catch((err) => console.error(err));
});
console.error(`watching ${ledgerPath} → ${url}`);

async function flush() {
  if (sending) return;
  sending = true;
  try {
    if (!existsSync(ledgerPath)) return;
    const text = readFileSync(ledgerPath, "utf8");
    const lines = text.split("\n");
    let offset = existsSync(offsetPath) ? Number(readFileSync(offsetPath, "utf8")) || 0 : 0;
    for (let i = offset; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) {
        offset = i + 1;
        continue;
      }
      const event = JSON.parse(line);
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(event),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`ingest ${res.status} at line ${i}: ${body}`);
      }
      offset = i + 1;
      writeFileSync(offsetPath, String(offset), "utf8");
      console.error(`sent ${event.kind} ${event.cycle_id}`);
    }
  } finally {
    sending = false;
  }
}

function loadEnv(path) {
  if (!existsSync(path)) return;
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const i = t.indexOf("=");
    if (i < 1) continue;
    const key = t.slice(0, i).trim();
    const val = t.slice(i + 1).trim();
    if (!process.env[key]) process.env[key] = val;
  }
}
