Work in `/workspace/repo`.

I maintain an external KV connector and am moving it from the pre-v0.12 API to a current vLLM release. The engine still falls back to the old two-argument constructor, so an outdated plugin appears to load and only fails later during initialization. That makes the actual migration problem hard to find.

Please finish removing that API from the factory and the connector base class. Current connectors should receive the engine's resolved KV-cache configuration, using the same object rather than a copy or a replacement. Reject an old constructor before its initialization code runs, and give the plugin author enough information to update it.

Each connector creation should invoke the constructor once. Keep scheduler and worker connectors working, including current plugins that inherit or forward their constructor. Repeated initialization of an active worker connector should reuse it; shutdown should close it, and the next initialization should create a fresh instance with the new configuration.

Normal Python argument errors and exceptions raised inside a current plugin should still reach the caller without being swallowed or turned into migration errors. Neither should trigger a compatibility retry. Don't break connectors that already follow the supported constructor contract.
