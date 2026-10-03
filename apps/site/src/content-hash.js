// Hash the exact UTF-8 bytes that were selected or fetched.  The parsed JSON
// is validated separately; re-serializing it would not prove byte identity.
export async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function utf8Bytes(text) {
  return new TextEncoder().encode(text);
}
