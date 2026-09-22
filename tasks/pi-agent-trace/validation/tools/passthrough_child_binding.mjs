// Explicitly selected only for reviewed transparent or missing-feature diagnostics.
// Ordinary child-process inheritance; no repair or private API introspection.
export async function childEnvironment({ env }) {
  return env;
}
