# API reference

Every record call the kit's samples make to a retailer's iVendNext, one section per address, from the kit's API description ([`api/openapi.yaml`](../../api/openapi.yaml)). This page is built from that file, so the two cannot disagree. The few calls that are not record calls are elsewhere: the `ivendnext_mpos.api.v1` methods, the engine's own functions under iVendNext names, are listed in [`api/README.md`](../../api/README.md), and the event feed is in its recipe.

**Everything you can call, on one page.** [What you can use](map.md) is the developer's map: every endpoint your app calls and every one iVendNext calls on your service, everything a manifest can add and every screen. [Record types](site:records/index.html) gives each record type an app reads or writes with its fields: which are required, which are read-only, and what each links to.

**How every call signs in.** Each call runs as your app's own integration user, with its key in one header: `Authorization: token <api key>:<api secret>`. It sees only what that user's role allows: a record the role cannot read answers `403`, a missing one `404`. The address is the retailer's own, `https://<site>`. [Security and the handshake](security.md) says how your app gets the user and its key.

**Try them.** `api/collection/run.sh` sends every call with `curl` alone, against your sandbox ([Get started](start.md), step 3).

{{api: reference}}
