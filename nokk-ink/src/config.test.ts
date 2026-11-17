import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { loadConfig, saveConfig } from "./config.js";

test("salva la configurazione senza perdere chiavi sconosciute", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "nokk-ink-config-"));
  const file = path.join(directory, "cli.json");
  fs.writeFileSync(file, JSON.stringify({
    base_url: "http://127.0.0.1:8000",
    theme: "scuro",
    bell_on_finish: true,
  }));
  const config = loadConfig(file);
  assert.equal(config.bellOnFinish, true);
  config.autoApprove = false;
  saveConfig(config, file);
  const saved = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
  assert.equal(saved.theme, "scuro");
  assert.equal(saved.auto_approve, false);
  assert.equal(saved.bell_on_finish, true);
  fs.rmSync(directory, { recursive: true, force: true });
});
