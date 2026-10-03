import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { sha256Hex, utf8Bytes } from "../src/content-hash.js";

test("hashes the fixture's exact UTF-8 bytes", async () => {
  const text = await readFile(new URL("../../../contracts/viewer/v1/fixtures/synthetic-race.json", import.meta.url), "utf8");
  assert.equal(await sha256Hex(utf8Bytes(text)), "9070dd48ab3fcbb21fb5da44d3af53235212b69ee3c634d20af4b5afbdb35845");
});

test("whitespace changes the byte hash", async () => {
  assert.notEqual(await sha256Hex(utf8Bytes("{}")), await sha256Hex(utf8Bytes("{}\n")));
});
