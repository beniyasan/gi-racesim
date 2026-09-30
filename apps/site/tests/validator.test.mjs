import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { ContractError, validateBundle } from "../src/validator.js";

const fixture = JSON.parse(await readFile(new URL("../../../contracts/viewer/v1/fixtures/synthetic-race.json", import.meta.url)));
const schema = JSON.parse(await readFile(new URL("../../../contracts/viewer/v1/schema.json", import.meta.url)));

test("viewer contract accepts the shared synthetic fixture", () => {
  assert.equal(validateBundle(fixture, schema).schema_version, "viewer/v1");
});

test("viewer contract rejects an unidentified result", () => {
  const broken = structuredClone(fixture);
  delete broken.model_id;
  assert.throws(() => validateBundle(broken, schema), ContractError);
});

test("viewer contract rejects a malformed group via schema", () => {
  const broken = structuredClone(fixture);
  broken.simulation.representative_trials[0].corners[0].groups[0].members = [];
  assert.throws(() => validateBundle(broken, schema), ContractError);
});
