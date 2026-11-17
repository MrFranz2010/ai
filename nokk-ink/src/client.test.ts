import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { NokkClient } from "./client.js";

async function server(): Promise<{ url: string; close: () => Promise<void>; seen: string[] }> {
  const seen: string[] = [];
  const instance = http.createServer((request, response) => {
    seen.push(`${request.method} ${request.url}`);
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/api/v1/chat") {
      response.end(JSON.stringify({ job_id: "job_123456" }));
      return;
    }
    if (request.url === "/api/v1/jobs/job_123456") {
      response.end(JSON.stringify({ status: "complete", reply: "ok" }));
      return;
    }
    response.statusCode = 404;
    response.end(JSON.stringify({ error: "non trovato" }));
  });
  await new Promise<void>((resolve) => instance.listen(0, "127.0.0.1", resolve));
  const address = instance.address();
  if (!address || typeof address === "string") throw new Error("porta non disponibile");
  return {
    url: `http://127.0.0.1:${address.port}`,
    seen,
    close: () => new Promise((resolve) => instance.close(() => resolve())),
  };
}

test("usa le rotte v1, avvia un job e ne legge lo stato", async () => {
  const mock = await server();
  try {
    const client = new NokkClient(mock.url, "chiave");
    const id = await client.startChat([{ role: "user", content: "ciao" }], {
      mode: "codice",
      stream: true,
      localTerminal: true,
    });
    assert.equal(id, "job_123456");
    const job = await client.job(id);
    assert.equal(job.status, "complete");
    assert.equal(job.reply, "ok");
    assert.deepEqual(mock.seen, ["POST /api/v1/chat", "GET /api/v1/jobs/job_123456"]);
  } finally {
    await mock.close();
  }
});

test("un errore HTTP espone un messaggio leggibile", async () => {
  const mock = await server();
  try {
    const client = new NokkClient(mock.url, "chiave");
    await assert.rejects(() => client.request("GET", "/missing"), /HTTP 404/);
  } finally {
    await mock.close();
  }
});
