import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { cleanToolMarkup, collectFileContext, extractRunCommands, needsSudo, runLocal } from "./local.js";

test("estrae i comandi nokk-run e accetta la chiusura XML", () => {
  const reply = [
    "Prima eseguo:",
    "```nokk-run",
    "pwd",
    "```",
    "Poi:",
    "```nokk-run",
    "echo ciao",
    "</parameter>",
  ].join("\n");
  assert.deepEqual(extractRunCommands(reply), ["pwd", "echo ciao"]);
});

test("rimuove i tag degli strumenti e riconosce sudo", () => {
  assert.equal(cleanToolMarkup("<parameter>ls -la</parameter>"), "ls -la");
  assert.equal(needsSudo("sudo systemctl restart nokk"), true);
  assert.equal(needsSudo("echo sudo"), false);
  assert.equal(needsSudo("ls && sudo whoami"), true);
});

test("legge i file citati con @ e ignora le email", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "nokk-ink-file-"));
  fs.writeFileSync(path.join(directory, "nota.txt"), "contenuto locale\n");
  assert.match(collectFileContext("guarda @nota.txt", directory), /contenuto locale/);
  assert.equal(collectFileContext("scrivi a mario@example.com", directory), "");
  fs.rmSync(directory, { recursive: true, force: true });
});

test("annulla davvero un comando locale lungo", async () => {
  const controller = new AbortController();
  const started = Date.now();
  const pending = runLocal("sleep 5", process.cwd(), undefined, controller.signal);
  setTimeout(() => controller.abort(), 100);
  const result = await pending;
  assert.equal(result.cancelled, true);
  assert.equal(result.exitCode, 130);
  assert.ok(Date.now() - started < 2500, "il processo sarebbe dovuto terminare subito");
});
