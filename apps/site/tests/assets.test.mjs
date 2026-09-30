import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import test from "node:test";

const siteRoot = new URL("../", import.meta.url);
const contractRoot = new URL("../../contracts/viewer/v1/", siteRoot);
const app = readFileSync(new URL("src/app.js", siteRoot), "utf8");
const html = readFileSync(new URL("index.html", siteRoot), "utf8");

test("literal fetch targets resolve under the documented static-server root", () => {
  const targets = [...app.matchAll(/fetch\("(\.\/[^"\n]+)"/g)].map((match) => match[1]);
  assert.ok(targets.length >= 2, "expected schema and fixture fetch paths");
  for (const target of targets) {
    const file = new URL(target, siteRoot);
    assert.ok(file.href.startsWith(siteRoot.href));
    assert.ok(statSync(file).isFile(), target);
  }
});

test("favicon, stylesheet and module exist under the same root", () => {
  const targets = [...html.matchAll(/(?:src|href)="(\.\/[^"\n]+)"/g)].map((match) => match[1]);
  assert.ok(targets.length >= 3);
  for (const target of targets) assert.ok(statSync(new URL(target, siteRoot)).isFile(), target);
});

test("published schema and fixture match their contract sources", () => {
  for (const name of ["schema.json", "fixtures/synthetic-race.json"]) {
    const source = readFileSync(new URL(name, contractRoot), "utf8");
    const published = readFileSync(new URL(`public/${name}`, siteRoot), "utf8");
    assert.equal(published, source, name);
  }
});
