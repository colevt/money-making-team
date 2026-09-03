#!/usr/bin/env node
/**
 * Append one ledger event from a Grok bot.
 * Usage: node tools/append-event.mjs '{"kind":"quiet",...}'
 *        node tools/append-event.mjs --file ./payload.json
 */
import { spawnSync } from "node:child_process";
import { appendFileSync, readFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
loadEnv(join(root, ".env"));

const ledgerPath = resolve(process.env.LEDGER_PATH || join(root, "ledger", "events.jsonl"));

const raw = readPayload(process.argv.slice(2));
const event = typeof raw === "string" ? JSON.parse(raw) : raw;
checkContract(event);

mkdirSync(dirname(ledgerPath), { recursive: true });
appendFileSync(ledgerPath, JSON.stringify(event) + "\n", "utf8");
console.error(`appended ${event.kind} cycle=${event.cycle_id} → ${ledgerPath}`);

function checkContract(e) {
  const r = spawnSync(
    "python3",
    [join(root, "tools", "ledger_contract.py"), "--ledger", ledgerPath],
    { input: JSON.stringify(e), encoding: "utf8" }
  );
  if (r.status !== 0) {
    const msg = (r.stderr || r.stdout || "invalid event").trim();
    console.error(msg);
    process.exit(1);
  }
}

function readPayload(args) {
  if (args[0] === "--file") {
    return readFileSync(args[1], "utf8");
  }
  if (args[0] && args[0] !== "-") return args[0];
  return readFileSync(0, "utf8");
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
