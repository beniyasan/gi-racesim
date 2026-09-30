// JSON Schema subset and semantic constraints mirror the Python validator.
// No schema URL or data URL is ever fetched by validation.
export const MAX_BYTES = 5 * 1024 * 1024;
export class ContractError extends Error {}
const requireThat = (ok, message) => { if (!ok) throw new ContractError(message); };
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const type = (value, kind) => ({
  null: value === null, boolean: typeof value === "boolean", object: object(value),
  array: Array.isArray(value), string: typeof value === "string",
  number: typeof value === "number" && Number.isFinite(value), integer: Number.isInteger(value),
}[kind]);

function validTime(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) return false;
  const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1]
    && hour < 24 && minute < 60 && second < 60 && Number.isFinite(Date.parse(value));
}

function check(value, schema, root, path = "$") {
  if (schema === undefined) throw new ContractError(`${path}: schema missing`);
  if (schema.$ref) return check(value, root.$defs[schema.$ref.replace("#/$defs/", "")], root, path);
  if (schema.anyOf) {
    for (const option of schema.anyOf) {
      try { check(value, option, root, path); return; } catch (error) { if (!(error instanceof ContractError)) throw error; }
    }
    throw new ContractError(`${path}: invalid shape`);
  }
  if ("const" in schema) requireThat(value === schema.const, `${path}: unsupported constant`);
  if (schema.enum) requireThat(schema.enum.includes(value), `${path}: invalid enum`);
  if (schema.type) requireThat([schema.type].flat().some(kind => type(value, kind)), `${path}: invalid type`);
  if (object(value)) {
    const props = schema.properties ?? {};
    requireThat((schema.required ?? []).every(key => Object.hasOwn(value, key)), `${path}: missing field`);
    if (schema.additionalProperties === false) requireThat(Object.keys(value).every(key => Object.hasOwn(props, key)), `${path}: unknown field`);
    for (const key of Object.keys(value)) if (Object.hasOwn(props, key)) check(value[key], props[key], root, `${path}.${key}`);
  } else if (Array.isArray(value)) {
    requireThat(value.length >= (schema.minItems ?? 0) && value.length <= (schema.maxItems ?? Infinity), `${path}: invalid length`);
    value.forEach((item, index) => check(item, schema.items, root, `${path}[${index}]`));
  } else if (typeof value === "string") {
    const length = [...value].length;
    requireThat(length >= (schema.minLength ?? 0) && length <= (schema.maxLength ?? Infinity), `${path}: invalid length`);
    if (schema.pattern) requireThat(new RegExp(schema.pattern, "u").test(value), `${path}: invalid string`);
    if (schema.format === "date-time") requireThat(validTime(value), `${path}: invalid timestamp`);
  } else if (typeof value === "number") {
    requireThat(Number.isFinite(value) && value >= (schema.minimum ?? -Infinity) && value <= (schema.maximum ?? Infinity), `${path}: out of bounds`);
    if ("exclusiveMinimum" in schema) requireThat(value > schema.exclusiveMinimum, `${path}: must be positive`);
  }
}

const unique = (values, message) => requireThat(new Set(values).size === values.length, message);
const increasing = values => values.every((value, index) => index === 0 || values[index - 1] < value);
function laps(lap, distance) {
  requireThat(lap.segment_ends_m.length === lap.values_s.length, "lap lengths differ");
  requireThat(increasing(lap.segment_ends_m) && lap.segment_ends_m.at(-1) === distance, "lap endpoints must increase and cover distance");
}
function corners(items, roster) {
  unique(items.map(corner => corner.checkpoint), "duplicate checkpoint");
  for (const corner of items) {
    const accounted = [...corner.unobserved_gate_numbers];
    if (accounted.length) requireThat(corner.unknown_reason !== null, "missing runners need an explanation");
    corner.groups.forEach((group, index) => {
      const members = group.members;
      accounted.push(...members);
      if (group.inner_to_outer !== null) {
        unique(group.inner_to_outer, "duplicate inner position");
        requireThat(group.inner_to_outer.length === members.length && group.inner_to_outer.every(number => members.includes(number)), "inner order must be a permutation of members");
      }
      requireThat(group.marked_leader === null || members.includes(group.marked_leader), "leader outside group");
      requireThat((group.gap_from_previous === null) === (index === 0), "only first group has no preceding gap");
    });
    unique(accounted, "runner appears twice at a checkpoint");
    requireThat(accounted.length === roster.size && accounted.every(number => roster.has(number)), "checkpoint must account for roster");
  }
}

export function validateBundle(bundle, schema) {
  check(bundle, schema, schema);
  const { race, simulation } = bundle;
  unique(race.runners.map(runner => runner.gate_no), "duplicate gate number");
  unique(race.runners.map(runner => runner.horse_id), "duplicate horse id");
  requireThat(Date.parse(bundle.as_of) < Date.parse(race.start_at), "as_of must precede start");
  requireThat(Date.parse(bundle.generated_at) >= Date.parse(bundle.as_of), "generation predates inputs");
  if (bundle.mode === "prospective") requireThat(Date.parse(bundle.generated_at) < Date.parse(race.start_at), "prospective result must precede start");
  if (bundle.origin !== "synthetic") requireThat(bundle.model_id !== null && bundle.producer_code_commit !== "0".repeat(40), "prediction needs model and code versions");
  requireThat(simulation.completed_trials <= simulation.total_trials, "completed trials exceed attempts");
  requireThat(simulation.representative_trials.length <= simulation.completed_trials, "representatives exceed completed trials");
  unique(simulation.representative_trials.map(trial => trial.trial_id), "duplicate representative trial");
  const roster = new Set(race.runners.map(runner => runner.gate_no));
  for (const trial of simulation.representative_trials) { laps(trial.laps, race.distance_m); corners(trial.corners, roster); }
  const ends = simulation.lap_quantiles.map(quantile => quantile.segment_end_m);
  requireThat(increasing(ends) && (!ends.length || ends.at(-1) === race.distance_m), "invalid aggregate endpoints");
  for (const quantile of simulation.lap_quantiles) {
    const values = [quantile.p10_s, quantile.p50_s, quantile.p90_s];
    requireThat(quantile.sample_count <= simulation.completed_trials, "aggregate sample exceeds completed trials");
    requireThat(quantile.sample_count === 0 ? values.every(value => value === null) : values.every(value => value !== null) && values.every((value, index) => !index || values[index - 1] <= value), "invalid quantiles");
  }
  if (bundle.observations.laps !== null) laps(bundle.observations.laps, race.distance_m);
  corners(bundle.observations.corners, roster);
  return bundle;
}
