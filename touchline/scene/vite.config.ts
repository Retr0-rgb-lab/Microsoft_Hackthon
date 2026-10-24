import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { IncomingMessage, ServerResponse } from "node:http";
import { defineConfig, type Plugin } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const sampleDir = path.resolve(rootDir, "../data/samples/sample_25hz_10min");
const sampleFiles = ["metadata.json", "clip.jsonl", "events.jsonl"];

function sendSample(req: IncomingMessage, res: ServerResponse, next: (err?: unknown) => void) {
  const raw = decodeURIComponent((req.url ?? "/").split("?")[0] ?? "/");
  const rel = raw.replace(/^\/+/, "");
  if (!rel || rel.includes("/") || rel.includes("\\") || rel.includes("..")) {
    next();
    return;
  }
  const file = path.join(sampleDir, rel);
  if (!file.startsWith(sampleDir + path.sep)) {
    next();
    return;
  }
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
    next();
    return;
  }
  const ext = path.extname(file);
  const type =
    ext === ".json"
      ? "application/json; charset=utf-8"
      : ext === ".jsonl"
        ? "application/x-ndjson; charset=utf-8"
        : "application/octet-stream";
  res.statusCode = 200;
  res.setHeader("Content-Type", type);
  res.setHeader("Cache-Control", "no-cache");
  const stream = fs.createReadStream(file);
  stream.on("error", () => {
    if (!res.headersSent) res.statusCode = 500;
    res.end();
  });
  stream.pipe(res);
}

function samplePlugin(): Plugin {
  return {
    name: "synth-sample",
    configureServer(server) {
      server.middlewares.use("/sample", sendSample);
    },
    configurePreviewServer(server) {
      server.middlewares.use("/sample", sendSample);
    },
    generateBundle() {
      for (const name of sampleFiles) {
        const file = path.join(sampleDir, name);
        if (!fs.existsSync(file)) continue;
        this.emitFile({
          type: "asset",
          fileName: `sample/${name}`,
          source: fs.readFileSync(file),
        });
      }
    },
  };
}

export default defineConfig({
  plugins: [samplePlugin()],
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(rootDir, "index.html"),
        flow: path.resolve(rootDir, "flow.html"),
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
});
