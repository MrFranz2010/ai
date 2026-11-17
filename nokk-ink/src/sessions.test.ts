import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { loadSessions, saveSessions } from "./sessions.js";

test("salva e ricarica le sessioni mantenendo i messaggi nascosti", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "nokk-ink-"));
  const file = path.join(directory, "sessions.json");
  saveSessions(file, [{
    title: "Prova",
    createdAt: 123,
    messages: [
      { role: "user", content: "domanda" },
      { role: "user", content: "output locale", hidden: true },
      { role: "assistant", content: "risposta" },
    ],
  }]);
  const loaded = loadSessions(file);
  assert.equal(loaded.length, 1);
  assert.equal(loaded[0].title, "Prova");
  assert.equal(loaded[0].messages[1].hidden, true);
  fs.rmSync(directory, { recursive: true, force: true });
});
