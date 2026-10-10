# 7Sageer/sublink-worker — source-level notes

- **Repo**: <https://github.com/7Sageer/sublink-worker> (`git remote get-url origin` → `https://github.com/7Sageer/sublink-worker.git`)
- **Commit**: `a223b11c1e5991db2f0e0ab89f0c5c8384845d93`
- **Commit date**: `2026-09-25T00:09:55+08:00` — subject: `fix: avoid empty direct detour for sing-box 1.14 rule-set downloads (#431)`
- **App version**: `2.4.2` (`src/constants.js:3` → `export const APP_VERSION = '2.4.2';`)
- **Read-only clone**: `/tmp/sublink-worker` (never modified). All citations are `path:line` relative to the repo root.
- **Method**: `grep`/`glob`/`read` over the clone, plus **empirical execution** of the *unmodified* parser/builder modules via an in-memory Node module-resolution hook (no files written anywhere, clone untouched; `js-yaml` stubbed since `node_modules` is absent). Empirical results are marked **[RAN]**.

## LANGUAGE REALITY CHECK — the "TypeScript" description is WRONG

- **There are ZERO TypeScript files in the repository.** `find . -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.d.ts' \)` (excluding `.git`) → **no output**.
- `src/` extension census: **49 `.js` + 11 `.jsx`** = 60 files. No `tsconfig.json`, no `typescript` dependency, no `typecheck` script.
- `package.json` scripts: `"test": "vitest run"`, `"build:node": "... esbuild ... --outfile=dist/node-server.cjs"` — no compile/typecheck step. Dev deps are only `@cloudflare/vitest-pool-workers`, `esbuild`, `vitest`, `wrangler`.
- `AGENTS.md` / `CLAUDE.md` themselves describe the stack as "Hono（Web/JSX SSR）+ Vitest + Wrangler + esbuild + ioredis" — no TS anywhere.
- `package.json` also declares `"type": "module"` (ESM) and `"engines": { "node": ">=18" }`.
- **Consequence for the enquiry: any "strongly typed node model" question is answered a priori — there is no type system at all, and therefore no compile-time guarantee that a node field is understood by any generator.**

---

## Q1 — Node internal model

### What represents a parsed node
- A **plain, dynamically-shaped JavaScript object literal**, created fresh inside each protocol parser. There is **no class, no constructor, no schema, no validator, no interface, no TypeScript type**. The only invariant is a `type` string discriminator.
- Entry class is `ProxyParser`, a static-only class used purely as a dispatch table (`src/parsers/ProxyParser.js:24-36`):

```js
export class ProxyParser {
    static async parse(url, userAgent) {
        if (!url || typeof url !== 'string') {
            return undefined;
        }
        const trimmed = url.trim();
        const type = trimmed.split('://')[0].toLowerCase();
        const parser = protocolParsers[type];
        if (!parser) {
            return undefined;
        }
        return parser(trimmed, userAgent);
```

- **There is ONE canonical *shape family*, not one canonical *type*.** Each parser writes its own literal; nothing is shared or enforced. Common keys are `type`, `tag`, `server`, `server_port`, plus optional `tls`, `transport`, `tcp_fast_open`. Everything else is protocol-specific.
- The documented (prose-only) return convention is in `AGENTS.md`:
  > 返回值约定：
  > - 协议 parser：`{ tag, type, ...protocolFields }`

### Field inventory (all verified by reading the parsers; several confirmed by **[RAN]**)

| Field | Where set | Shape / notes |
| --- | --- | --- |
| `type` | every parser | string discriminator: `shadowsocks`, `vmess`, `vless`, `hysteria2`, `tuic`, `trojan`, `anytls` |
| `tag` | every parser | node display name |
| `server`, `server_port` | every parser | `server_port` is an **int** (from `parseServerInfo`, `src/utils.js:269`) |
| `tcp_fast_open` | ss/vmess/vless/trojan only (`false` hardcoded) | boolean; **tuic/hysteria2/anytls use `fast_open` instead** — inconsistent naming inside the same model |
| `tls` | ss? no — vmess/vless/trojan/hysteria2/tuic/anytls | object, see below |
| `transport` | vmess/vless/trojan | object, see below |
| `flow` | vless/trojan/tuic | free string, e.g. `xtls-rprx-vision` (`vlessParser.js:29`, `trojanParser.js:22`, `tuicParser.js:23`) |
| `udp` | vless/anytls (spread-in), yaml-converter (all types) | boolean, conditionally added via `...(udp !== undefined ? { udp } : {})` (`vlessParser.js:30`) |
| `plugin`, `plugin_opts` | shadowsocks only | flat sibling keys, `plugin_opts` is a **snake_case** object (`shadowsocksParser.js:74-80`) |
| `obfs` | hysteria2 | `{ type, password }` (`hysteria2Parser.js:25-29`) |
| `auth`, `recv_window_conn`, `up`, `down`, `ports`, `hop_interval`, `alpn`, `fast_open` | hysteria2 | flat, mix of snake_case and bare (`hysteria2Parser.js:41-48`) |
| `uuid`, `password`, `alter_id`, `security`, `method` | per protocol | `alter_id` for vmess (`vmessParser.js:87`) |
| `congestion_control`, `udp_relay_mode`, `zero_rtt`, `reduce_rtt`, `disable_sni` | tuic | `tuicParser.js:21-28` |
| `idle-session-check-interval`, `idle-session-timeout`, `min-idle-session` | anytls | **kebab-case** keys — a third naming convention (`anytlsParser.js:87-89`) |
| `network` | YAML/Surge converters only | e.g. `convertYamlProxyToObject.js:19,62,119,171`; **URI parsers never set it** |
| `packet_encoding` | YAML converter only | `convertYamlProxyToObject.js:67,122` |

### TLS / Reality / flow / fingerprint expression
`createTlsConfig` is the shared TLS builder for URI schemes (`src/utils.js:289-310`):

```js
export function createTlsConfig(params) {
	let tls = { enabled: false };
	if (params.security && params.security !== 'none') {
		tls = {
			enabled: true,
			server_name: params.sni || params.host,
			insecure: !!params?.allowInsecure || !!params?.insecure || !!params?.allow_insecure,
			// utls: {
			//   enabled: true,
			//   fingerprint: "chrome"
			// },
		};
		if (params.security === 'reality') {
			tls.reality = {
				enabled: true,
				public_key: params.pbk,
				short_id: params.sid,
			};
		}
	}
	return tls;
}
```

- **Reality** is a nested `tls.reality = { enabled, public_key, short_id }` — only ever these three keys.
- **flow** lives **outside** `tls`, as a top-level `flow` string.
- **fingerprint** is `tls.utls = { enabled: true, fingerprint }`.
- **headers** are `transport.headers` — but the shape is **inconsistent across parsers**: URI parsers always produce a *string-valued* `{ host }` (`src/utils.js:316` → `...(params.host && { 'headers': { 'host': params.host } })`), while the vmess parser produces `{ host: string[] }` and arbitrary header arrays (`vmessParser.js:8-26`), and the YAML converter passes `ws-opts.headers` through untouched (`convertYamlProxyToObject.js:38`).
- **plugin** is not part of `tls`/`transport` at all — it is a flat pair on the node (`shadowsocksParser.js:63-83`).

### Concrete parser output **[RAN]** (real execution, truncated to essentials)
```
trojan://pw@h.example:443?security=reality&sni=s.example&pbk=PUBKEY&sid=abcd&spx=%2Fspider
        &fp=firefox&flow=xtls-rprx-vision&type=grpc&serviceName=gsvc#TrojanReality
→ { type:'trojan', tag:'TrojanReality', server:'h.example', server_port:443, password:'pw',
    tcp_fast_open:false,
    tls:{ enabled:true, server_name:'s.example', insecure:false,
          reality:{ enabled:true, public_key:'PUBKEY', short_id:'abcd' } },
    transport:{ type:'grpc', service_name:'gsvc' },
    flow:'xtls-rprx-vision' }
```
Note what is **already absent at parse time**: `spx=/spider` is gone (never read), `fp=firefox` is gone (never read by `createTlsConfig`). For the same input with `vless://`, the model instead contains `utls:{enabled:true,fingerprint:'chrome'}` — the user's `fp=firefox` is *replaced by a hardcoded literal* (`vlessParser.js:8-14`):

```js
    const tls = createTlsConfig(params);
    if (tls.reality) {
        tls.utls = {
            enabled: true,
            fingerprint: 'chrome'
        };
    }
```

### Is there a single canonical node type or one shape per protocol?
- **One shape per protocol parser** (7 URI protocols + 2 config converters), over a shared loose convention. Notable divergences *within the same model*:
  - `tcp_fast_open` (ss/vmess/vless/trojan) vs `fast_open` (hysteria2/tuic/anytls).
  - snake_case (`server_port`, `alter_id`, `plugin_opts`, `tls.server_name`) vs kebab-case (`idle-session-timeout`, `hop_interval` is snake while `'idle-session-check-interval'` is kebab).
  - `network` exists only for config-file inputs, never for URI inputs.
- The **only** per-protocol contract is which `switch`/`case` arms each builder implements (see Q3/Q4). Unknown/new keys therefore cannot be detected — nothing enumerates the legal key set.

---

## Q2 — URI parsing

### Entry point
- `ProxyParser.parse(url, userAgent)` — `src/parsers/ProxyParser.js:24-36` (quoted in Q1).
- Called from exactly three places, all in `src/builders/BaseConfigBuilder.js:133,148,168`.
- The scheme is extracted with a bare string split: `const type = trimmed.split('://')[0].toLowerCase();` (`ProxyParser.js:30`).

### Supported schemes — the complete dispatch table
`src/parsers/ProxyParser.js:10-22`:

```js
const protocolParsers = {
    ss: parseShadowsocks,
    vmess: parseVmess,
    vless: parseVless,
    hysteria: parseHysteria2,
    hysteria2: parseHysteria2,
    hy2: parseHysteria2,
    http: fetchSubscription,
    https: fetchSubscription,
    trojan: parseTrojan,
    tuic: parseTuic,
    anytls: parseAnytls
};
```

- **Supported node protocols: `ss`, `vmess`, `vless`, `hysteria`/`hysteria2`/`hy2`, `trojan`, `tuic`, `anytls`** — 7 distinct protocols from 11 schemes.
- **`http:`/`https:` are NOT HTTP-proxy nodes** — they dispatch to `fetchSubscription`, i.e. they are *subscription URLs*. There is **no HTTP proxy node type and no SOCKS node type at all**.
- **NOT supported at all: `ssr`, `socks`, `socks5`, `http-proxy`, `wireguard`, `snell`, `ssh`, `mieru`.** Verified by grep: the only `socks5` hits in `src/` are Surge's *local listener* settings (`src/config/surgeConfig.js:10,12` → `'wifi-access-socks5-port'`, `'socks5-listen'`), not a node type.
- Also note the README's protocol claim for cross-check: "ShadowSocks • VMess • VLESS • Hysteria2 • Trojan • TUIC" (`README.md`) — it omits `anytls`, which the code **does** support, so the README is *stale/understating*, not authoritative.

### Unknown query parameters / unsupported keys — silently ignored, never logged, never preserved
Three-stage mechanism:

1. **All params are captured**, unfiltered, into a plain object (`src/utils.js:272-287`):
```js
export function parseUrlParams(url) {
	const [, rest] = url.split('://');
	const [addressPart, ...remainingParts] = rest.split('?');
	const paramsPart = remainingParts.join('?');

	const [paramsOnly, ...fragmentParts] = paramsPart.split('#');
	const searchParams = new URLSearchParams(paramsOnly);
	const params = Object.fromEntries(searchParams.entries());
```
2. **Each parser then reads a hand-picked allowlist** and returns an *explicit object literal*, so every unread key — unknown or merely unimplemented — is discarded when the local `params` object goes out of scope. E.g. `vlessParser.js:20-31` returns only `type, tag, server, server_port, uuid, tcp_fast_open, tls, transport, flow, udp`. There is no spread of `params`, no `...rest`, no catch-all.
3. **Nothing reports the discard.** Grep across `src/` for `unsupportedParams`, `unknownParam`, `ignoredParam`, `warn` in any parser → **no such mechanism exists**. The only parser-level logging in the whole URI path is a hard failure log (`shadowsocksParser.js:127-130`):
```js
    } catch (e) {
        console.error('Failed to parse shadowsocks URL:', e);
        return null;
    }
```
`anytlsParser.js` additionally uses `new URL(url)` and `getFirstParam(params, [keyA, keyB, ...])` (lines 3-10), i.e. the same allowlist pattern with alias fallbacks.

**[RAN] confirmation** — `vless://...&mode=gun&extra=UNKNOWNVAL#VlessReality` produced a node object containing **neither** `mode` **nor** `extra`. Likewise `spx=/spider` (a *real, meaningful* Reality param) never reaches the model, because `createTlsConfig` reads only `pbk` and `sid` (`src/utils.js:301-307`).

**Known-parameter drops are equally silent and are not limited to "unknown" keys:**
- `fp=` (fingerprint) is honoured **only for anytls** (`anytlsParser.js:61-67`). For vless it is overwritten with the literal `'chrome'` when Reality is on (`vlessParser.js:10-13`); for trojan/vmess/tuic it is dropped because `createTlsConfig` never reads it (only the commented-out block at `utils.js:296-299` hints it once did).
- gRPC `mode=` is never read: `createTransportConfig` only reads `serviceName` for grpc (`utils.js:317-319`).
- `ss://` query strings are parsed by a second, independent hand-rolled extractor that reads **only** `plugin` (`shadowsocksParser.js:101-109`) — so e.g. `udp`/`tfo` on an `ss` URI are discarded.

---

## Q3 — Multi-target generation

### Targets that actually generate configs
| Target | Route | Generator | Base config |
| --- | --- | --- | --- |
| Sing-Box | `GET /singbox` (`src/app/createApp.jsx:71`) | `class SingboxConfigBuilder` (`src/builders/SingboxConfigBuilder.js:16`) | `SING_BOX_CONFIG`, `SING_BOX_CONFIG_V1_11` (`src/config/singboxConfig.js`) |
| Clash / mihomo | `GET /clash` (`createApp.jsx:127`) | `class ClashConfigBuilder` (`src/builders/ClashConfigBuilder.js:50`) | `CLASH_CONFIG` (`src/config/clashConfig.js`) |
| Surge | `GET /surge` (`createApp.jsx:176`) | `class SurgeConfigBuilder` (`src/builders/SurgeConfigBuilder.js:7`) | `SURGE_CONFIG` (`src/config/surgeConfig.js`) |

- **Yes: one generator file per real target**, all extending `BaseConfigBuilder` (`src/builders/BaseConfigBuilder.js:6`) and overriding the same method set (`AGENTS.md`: `getProxies()`、`getProxyName(proxy)`、`convertProxy(proxy)`、`addProxyToConfig(proxy)`、`addAutoSelectGroup(list)`、`addNodeSelectGroup(list)`、`addOutboundGroups(...)`、`addCustomRuleGroups(list)`、`addFallBackGroup(list)`、`addCountryGroups()`、`formatConfig()`).
- **There is NO separate `clashmeta` / `mihomo` target.** "clash" *is* the mihomo-flavoured target: it emits MRS rule-providers, `proxy-providers`, and `reality-opts` (mihomo-only fields) — see `ClashConfigBuilder.js:22-41` (MRS UA sniff) and `:205-208` (`reality-opts`).
- **`GET /xray` is NOT a generator.** `createApp.jsx:263-311` only fetches/decodes input URI lines and re-emits them Base64-encoded (`return c.text(encodeBase64(finalString), 200, responseHeaders);`). No node object is ever built, so this "target" is a pure passthrough and has no field-loss surface.
- **`GET /subconverter`** (`createApp.jsx:220`) emits an **external subconverter INI** (`src/config/subconverterConfig.js:37` → `export function generateSubconverterConfig(...)`): rules/groups only, no proxy conversion.
- Output encodings differ: Clash `yaml.dump(this.config)` (`ClashConfigBuilder.js:715`), Sing-Box `c.json(builder.config)` (`createApp.jsx:121`, config object returned from `formatConfig()` at `SingboxConfigBuilder.js:710`), Surge `c.text(builder.formatConfig())` (INI text).

### How a new target is added
There is **no registry, no plugin list, no capability table** — it requires coordinated edits in four places:
1. new base config module in `src/config/` (e.g. `xsConfig.js`) exported from `src/config/index.js:41-43`;
2. a new `*ConfigBuilder` class extending `BaseConfigBuilder` and implementing the abstract methods — `addProxyToConfig` is explicitly abstract (`BaseConfigBuilder.js:355-357`):
```js
    addProxyToConfig(proxy) {
        throw new Error('addProxyToConfig must be implemented in child class');
    }
```
3. a route in `src/app/createApp.jsx` (all three follow the same shape, e.g. `:176-218`);
4. optionally a short-link prefix `app.get('/x/:code', redirectHandler('xray'))` (`createApp.jsx:349-352`).
Note `AGENTS.md` documents recipes for adding a **protocol** and a **runtime**, but **documents no recipe for adding a target** — a real gap.

---

## Q4 — What happens when a target does NOT support a field ⭐

**Bottom line up front:** there are exactly **two** user-visible notices in the entire codebase, and *both are whole-node / whole-rule comments inside a Surge config* (`SurgeConfigBuilder.js:132` and `:437`). **Every field-level incompatibility is a completely silent drop**: no warning, no log, no header, no diagnostics field, no comment. The generated config simply lacks the field, and the node usually still looks present and valid.

### 4.0 The complete inventory of notice mechanisms that exist
Grep for `unsupported|not supported|warn|skip|exclude|drop|omit|ignor` across `src/` yields only these relevant hits:

**(a) Unknown proxy *type* for Surge** — `src/builders/SurgeConfigBuilder.js:131-133`:
```js
            default:
                surgeProxy = `# ${proxy.tag} - Unsupported proxy type: ${proxy.type}`;
        }
        return surgeProxy;
```
The comment is deliberately excluded from proxy groups so the INI stays syntactically valid (`SurgeConfigBuilder.js:31-43`):
```js
    getValidProxies() {
        return this.getProxies().filter(proxy =>
            typeof proxy === 'string' && !proxy.trimStart().startsWith('#')
        );
    }
    ...
    getProxyList() {
        return this.getValidProxies().map(proxy => this.getProxyName(proxy));
    }
```
**[RAN]** `anytls://` and `vless://` nodes produce exactly:
```
# AnyTLSNode - Unsupported proxy type: anytls
# VlessNode - Unsupported proxy type: vless
```
This is comment text in the body of the returned config — **not** an HTTP error, **not** a warning field, **not** a header.

**(b) `SRC-IP-CIDR` unsupported by Surge** — `SurgeConfigBuilder.js:437`:
```js
                    finalConfig.push(`# SRC-IP-CIDR not supported by Surge, skipped: ${safeValue}`);
```
(The only other `console.warn` about unsupported input is `convertSurgeProxyToObject.js:200`, which goes to the *server* log only — see 4.5.)

### 4.1 Surge: field-level drops — no `else`, so the branch simply doesn't exist
`SurgeConfigBuilder.convertProxy` (`:49-135`) emits only `ws` and `grpc` transports, guarded by `if / else if` with **no fallback arm** for vmess (`:72-79`) and trojan (`:92-99`):
```js
                if (proxy.transport?.type === 'ws') {
                    surgeProxy += `, ws=true, ws-path=${proxy.transport.path}`;
                    if (proxy.transport.headers) {
                        surgeProxy += `, ws-headers=Host:${proxy.transport.headers.host}`;
                    }
                } else if (proxy.transport?.type === 'grpc') {
                    surgeProxy += `, grpc-service-name=${proxy.transport.service_name}`;
                }
```
Any other transport type (`http`, `h2`, `xhttp`, `kcp`, `quic`, …) therefore **falls through silently and the transport is lost entirely**.

**[RAN]** concrete proof — trojan URI with `type=http&path=%2Fte&host=cdn.example`:
```
TrojanHttp = trojan, h2.example, 443, password=pw, sni=cdn.example
```
The path and host are gone; the line is indistinguishable from a plain Trojan node. No notice of any kind.

### 4.2 Surge: fields the builder never references (grep count = 0)
Grep counts per builder for the fields in question:

| field | `ClashConfigBuilder.js` | `SingboxConfigBuilder.js` | `SurgeConfigBuilder.js` |
| --- | --- | --- | --- |
| `reality` | 6 | 0 | **0** |
| `utls` | 3 | 0 | **0** |
| `fingerprint` | 3 | 0 | **0** |
| `flow` | 2 | 0 | **0** |
| `obfs` | 2 | 0 | **0** |
| `plugin` | 2 | 0 | **0** |
| `packet_encoding` | 1 | 2 | **0** |
| `xhttp` | 0 | 0 | **0** |

- For `SingboxConfigBuilder` a count of 0 means *passthrough* (the internal shape is already sing-box-shaped, and `convertProxy` only mutates a shallow copy).
- For `SurgeConfigBuilder` a count of 0 means **the field is dropped**, because Surge output is built by explicit string concatenation from a fixed field list (`:52-130`) and nothing else is ever read.

**[RAN] — the highest-value example (Reality silently downgraded to plain TLS in Surge).** Input:
```
trojan://pw@h.example:443?security=reality&sni=s.example&pbk=PUBKEY&sid=abcd&fp=firefox
        &flow=xtls-rprx-vision&type=grpc&serviceName=gsvc#TrojanReality
```
Internal model (correct, reality intact):
```json
{ "type":"trojan","tag":"TrojanReality","tls":{"enabled":true,"server_name":"s.example",
  "reality":{"enabled":true,"public_key":"PUBKEY","short_id":"abcd"}},
  "transport":{"type":"grpc","service_name":"gsvc"},"flow":"xtls-rprx-vision" }
```
Surge `[Proxy]` output:
```
TrojanReality = trojan, h.example, 443, password=pw, sni=s.example, grpc-service-name=gsvc
```
A substring scan of the **entire** generated Surge config returned `false` for every one of: `reality`, `flow`, `xtls`, `fingerprint`, `obfs`, `plugin`, `public-key`, `pbk`.
**The node survives with an ordinary-TLS flag, its Reality parameters are gone, and the user receives no indication whatsoever.** Because Surge has no Reality support, the node is emitted as a config that *looks* valid and will simply fail to connect — the user has no way to know why.

**[RAN] other Surge drops, same run:**
- SS + SIP003 plugin (`?plugin=obfs-local;obfs=http;obfs-host=cdn.example`) → `SSPlugin = ss, h.example, 8388, encrypt-method=aes-128-gcm, password=pw` — `plugin`/`plugin_opts` gone. (The internal model *had* `plugin:"obfs-local"` and `plugin_opts:{mode:"http",host:"cdn.example"}`.)
- Hysteria2 + obfs → `HY2Obfs = hysteria2, h.example, 443, password=pw, sni=s.example, skip-cert-verify=true` — `obfs.type:"salamander"` and `obfs.password` gone.

### 4.3 Sing-Box: silent `delete` statements, documented only in code comments
`SingboxConfigBuilder.convertProxy` (`:104-179`) strips incompatible fields with bare `delete`, never warning. The comments admit the loss but never reach the user:

```js
        // Strip Clash-only / mis-typed fields that conflict with sing-box semantics.
        // `udp` is Clash-only. Top-level `network` in sing-box is a TCP/UDP allowlist
        // (NetworkList in option/types.go); a stray "tcp" silently disables UDP for
        // every group that selects this node — including DNS hijack and fakeip.
        delete sanitized.udp;
        delete sanitized.network;
```
(`SingboxConfigBuilder.js:126-131`)

```js
        // Remove packet_encoding for now - it's version-specific in sing-box
        // xudp is default in newer versions
        delete sanitized.packet_encoding;
```
(`:146-148`)

```js
            delete sanitized.auth;
            delete sanitized.recv_window_conn;
            delete sanitized.fast_open;
```
(`:173-175`, inside the `hysteria2` branch whose own comment says:)
```js
            // sing-box names port-hopping/bandwidth fields differently from the
            // share-link shape, and rejects unknown fields outright
```
(`:151-152`)

Root-level `alpn` is relocated or deleted (`:133-144`), and anytls kebab keys are renamed + numeric seconds converted to Duration strings (`:110-124`). **[RAN]** all confirmed: an `anytls` node with `udp:true, idle-session-check-interval:30, idle-session-timeout:120` emerged as `idle_session_check_interval:"30s", idle_session_timeout:"120s", min_idle_session:5` with `udp` and `network` absent.

**An inconsistency worth flagging:** the same function deletes `udp`/`network`/`packet_encoding` but **does not** delete `plugin` / `plugin_opts` / `tcp_fast_open`. **[RAN]** an `ss://…?plugin=obfs-local;…` node passed through sing-box conversion as:
```json
{ "tag":"SSPlugin","type":"shadowsocks","server":"h.example","server_port":8388,
  "method":"aes-128-gcm","password":"pw","tcp_fast_open":false,
  "plugin":"obfs-local","plugin_opts":{"mode":"http","host":"cdn.example"} }
```
Given the file's own claim that sing-box "rejects unknown fields outright" (`:152`), Clash-only `plugin`/`plugin_opts` are still emitted into a sing-box config verbatim. *I did not run a sing-box binary, so I cannot assert the kernel's reaction (see UNKNOWN) — but the asymmetry between the strip-list and the file's stated strategy is observable in code.*

### 4.4 Clash: three distinct silent-loss mechanisms
**(a) Unknown node type is emitted raw into the YAML** — `ClashConfigBuilder.js:306-307`:
```js
            default:
                return proxy; // Return as-is if no specific conversion is defined
```
The internal object (with `server_port`, `alter_id`, `plugin_opts`, …) is returned unconverted and pushed straight into `config.proxies`, producing mihomo-invalid keys. No warning. (Note the contrast with Surge, which at least emits a comment.)

**(b) Mismatched transport options are assigned `undefined`** — `ClashConfigBuilder.js:158-186`:
```js
                    'ws-opts': proxy.transport?.type === 'ws'
                        ? { path: proxy.transport.path, headers: proxy.transport.headers }
                        : undefined,
                    'http-opts': proxy.transport?.type === 'http' ? (() => { ... })() : undefined,
                    'grpc-opts': proxy.transport?.type === 'grpc'
                        ? { 'grpc-service-name': proxy.transport.service_name }
                        : undefined,
                    'h2-opts': proxy.transport?.type === 'h2' ? { path: ..., host: ... } : undefined,
```
`js-yaml`'s `dump` omits `undefined` values, so the block silently disappears. There is **no `xhttp-opts` arm at all** (grep `xhttp` in `src/` → **0 hits**).

**[RAN] — xhttp/grpc example.** Input `vless://…&type=xhttp&path=%2Fx&host=cdn.example&mode=packet-up` produced the internal model `transport:{type:"xhttp",path:"/x",headers:{host:"cdn.example"}}`; Clash conversion emitted:
```json
{ "name":"X","type":"vless","server":"h.example","port":443,"uuid":"u","tls":true,
  "servername":"s.example","network":"xhttp","tfo":false,"skip-cert-verify":false,"udp":true }
```
`network: xhttp` is copied verbatim from the unvalidated `transport.type` (`src/utils.js:314` → `type: params.type`), but **the path `/x` and host `cdn.example` are gone** and no `xhttp-opts` is written. The node stays in the config looking healthy, will not connect, and nothing tells the user why. Note also that `mode=packet-up` never even reached the model (Q2).

**(c) Same-URI example where Clash *does* preserve everything** — for contrast, **[RAN]** the trojan+Reality node becomes fully lossless in Clash:
```json
{ "name":"T","type":"trojan","server":"h.example","port":443,"password":"pw","tls":true,
  "sni":"s.example","network":"grpc","reality-opts":{"public-key":"PUBKEY","short-id":"abcd"},
  "grpc-opts":{"grpc-service-name":"gsvc"},"tfo":false,"skip-cert-verify":false,
  "flow":"xtls-rprx-vision","udp":true }
```
So capability loss is **target-specific**: Clash ≈ sing-box ≫ Surge.

### 4.5 Intake-side silent deletion (nodes vanish before any builder runs)
`convertYamlProxyToObject` returns `null` for any unrecognised `type` (`src/parsers/convertYamlProxyToObject.js:261-262`):
```js
        default:
            return null;
```
…and `parseClashYaml` then discards the nulls with no counter, log, or comment (`src/parsers/subscription/subscriptionContentParser.js:122-124`):
```js
            const proxies = parsed.proxies
                .map(p => convertYamlProxyToObject(p))
                .filter(p => p != null);
```
Same pattern for Surge input (`subscriptionContentParser.js:157-159`). **[RAN]** `convertYamlProxyToObject({type:'wireguard',…})` and `{type:'snell',…}` both → `null`.

**This behaviour is asserted as *intended* by the test suite** — `test/yaml-parsing.test.js:76-96`:
```js
        name: '混合类型与无效节点',
        description: '仅返回受支持类型的节点，忽略未知类型',
        input: `proxies:
  - name: Valid-SS
    ...
  - name: Invalid-Type
    type: unknown
    server: invalid.com
    port: 80`,
        expected: {
            proxyCount: 1,
            proxyTags: ['Valid-SS'],
            typeCount: { shadowsocks: 1 }
        }
```
i.e. "ignore unknown types" is the *specified* contract, with no assertion that anything is reported.

The only compile-time-ish warning in intake is `convertSurgeProxyToObject.js:200`:
```js
        default:
            console.warn(`Unsupported Surge proxy type: ${type}`);
            return null;
```
This is a **server-side console log**, invisible to the HTTP caller, and by then the node is also discarded by the `.filter(p => p != null)` above. Note also that `http`/`https`/`direct`/`reject`/`reject-tinygif` Surge lines return `null` *without* even that log (`convertSurgeProxyToObject.js:188-197`, comment `// Skip HTTP/HTTPS proxy types`).

### 4.6 Is there a channel through which the user *could* be told? No.
- The routes return **only** the config body plus optionally a `subscription-userinfo` header: `createApp.jsx:121` (`return c.json(builder.config);`), `:170` (`return c.text(builder.formatConfig(), 200, headers)` where `headers` only holds `Content-Type` and `subscription-userinfo`), `:214` (`return c.text(builder.formatConfig());`). There is **no** warnings header, no diagnostics field, no `X-Sublink-Dropped` style metadata.
- The i18n catalogs contain **no** user-facing string about unsupported/ignored/dropped anything (grep `unsupported|not supported|dropped|ignored` in `src/i18n/index.js` → **no hits**).
- So the answer to "does the converter tell the user anything?" is: **for a whole protocol type in Surge only, it writes a `#`-comment line into the config body; for every field-level incompatibility, in every target, it tells the user nothing at all and emits the field as simply missing.**

### 4.7 The one hard failure (for completeness)
Empty `url-test`/`fallback` groups make Clash reject a config, so the builder fails fast instead of silently emitting — `ClashConfigBuilder.js:640-661`:
```js
            const groupName = group?.name || '(unnamed group)';
            throw new InvalidConfigError(
                `Invalid proxy group "${groupName}": type "${group.type}" requires at least one proxy or provider reference`
            );
```
This is the **only** place where an unsupported situation becomes an error visible to the caller — and it is about group membership, not about a node field.

---

## Q5 — Admitted loss / known pain points / tests

### Comments admitting loss (real quotes)
- `SingboxConfigBuilder.js:146-147` — `// Remove packet_encoding for now - it's version-specific in sing-box` / `// xudp is default in newer versions`.
- `SingboxConfigBuilder.js:127-129` — explains that a stray `network: "tcp"` "silently disables UDP for every group that selects this node".
- `SingboxConfigBuilder.js:151-152` — `// sing-box names port-hopping/bandwidth fields differently from the share-link shape, and rejects unknown fields outright`.
- `SingboxConfigBuilder.js:108-109` — Mihomo kebab-case vs sing-box snake_case mismatch.
- `vlessParser.js:17` — `// `udp` is a Clash-only flag; ClashConfigBuilder reads it, SingboxConfigBuilder strips it.` (the codebase *does* track per-target field support — but only in prose, never in a data structure.)
- `utils.js:296-299` — the commented-out `utls` block (fingerprint emission was disabled at some point and left in place).
- `ClashConfigBuilder.js:22` — legacy Clash clients need YAML rule sets instead of MRS.
- No comment anywhere admits a *user-visible* loss report is missing.

### Docs
- **There is no known-limitations / caveats section.** Grep for `limitation|not support|unsupported|loss|known issue|caveat|局限|丢失` across `README.md`, `AGENTS.md`, `CLAUDE.md`, `.github/ISSUE_TEMPLATE/*.md` → **no hits**.
- `README.md` protocol list omits `anytls` (which is implemented), so the README is stale in both directions. Docs point to an external site (`https://sublink.works/`) for anything deeper — **not verifiable from this clone** (see UNKNOWN).

### Test suite — what is actually tested
- **38 test files, 5,023 lines** under `test/`. Runner: `vitest.config.js` using `@cloudflare/vitest-pool-workers` against `wrangler.toml` (`vitest.config.js`), i.e. tests execute inside a Workers-like pool via `createApp(runtime)` + `MemoryKVAdapter` (`AGENTS.md`).
- **No round-trip / fidelity tests exist.** Grep for `reparse|round.?trip|fidelity` in `test/` → **no matches**. Nothing parses its own generated output back.
- **No snapshot tests at all.** Grep for `toMatchSnapshot|toMatchInlineSnapshot` in `test/` → **no matches**.
- So it is **neither** true round-trip testing **nor** output snapshots. It is a set of **per-issue regression tests asserting specific fields / substrings** — e.g. `test/issue-297-vmess-network.test.js`, `test/issue-337-ss-cipher-decode.test.js`, `test/issue-388-trojan-tls.test.js`, `test/issue-428-hy2-port-hopping.test.js`.
- Tests that **encode the silent-drop behaviour as the expected contract**:
  - `test/udp-handling.test.js:34-52` — `describe('sing-box output should not contain udp field')`, `expect(converted.udp).toBeUndefined();`
  - `test/udp-handling.test.js:54-70` — root-level `alpn` is moved into `tls` for sing-box.
  - `test/udp-handling.test.js:73-91` — `describe('Clash output should preserve udp field')` (the per-target asymmetry is explicitly modelled).
  - `test/yaml-parsing.test.js:76-96` — unknown proxy type must be ignored (`proxyCount: 1`).
  - `test/surge-unsupported-proxy.test.js:12-40` — asserts the `# USA-VLESS - Unsupported proxy type` comment must **not** leak into proxy groups; the only requirement is that the config stays syntactically valid. Its docstring states the problem framing:
    > Problem: When subscription contains unsupported proxy types (like VLESS), the comment string "# USA-VLESS - Unsupported proxy type: vless" is incorrectly added to Proxy Groups, breaking the config syntax.
- Tests that exercise input formats: `test/singbox-input-parsing.test.js`, `test/surge-input-parsing.test.js`, `test/yaml-parsing.test.js`, `test/subconverter-endpoint.test.js`, `test/proxy-providers.test.js`, `test/proxy-groups-override.test.js`, `test/src-ip-cidr.test.js`, `test/country-group.test.js`.
- **Nothing tests that Reality survives to any target.** Grep `reality` in `test/` returns only: an incidental `server: 'reality.example'` (`test/proxy-helpers.test.js:9`), the two `security=reality` URIs in `test/surge-unsupported-proxy.test.js:15,127` where the node is asserted to be *excluded* from Surge output, and `reality-opts:` inside a YAML fixture whose assertions are only `proxyCount`/`typeCount` (`test/yaml-parsing.test.js:59,64-68`). **The exact class of loss described in Q4.2 is untested.**
- CI runs only install + test: `.github/workflows/test.yml` → `npm install`, `npm test`. No further steps.

---

## Q6 — What it does NOT do

| Question | Answer | Evidence |
| --- | --- | --- |
| Concept of a target **kernel version**? | **YES for sing-box only**; **NO for Clash/mihomo**; **NO for Surge** | see below |
| Runtime validation that the generated config is **accepted by the kernel**? | **NO** | see below |
| Notion of an **"unknown capability"** distinct from "unsupported"? | **NO** | see below |

### (a) Target kernel version — sing-box: yes
- Three explicit tiers: `'1.11' | '1.12' | '1.14'` (`SingboxConfigBuilder.js:28` → `this.singboxVersion = singboxVersion;  // '1.11', '1.12' or '1.14'`), resolved from the `singbox_version` / `sb_version` / `sb_ver` query param or the `sing-box/x.y.z` User-Agent (`createApp.jsx:89-93`).
- Tier resolution (`createApp.jsx:489-515`):
```js
function resolveSingboxConfigTier(version) {
    if (isSingboxLegacyConfig(version)) return '1.11';
    return isSingboxModernConfig(version) ? '1.14' : '1.12';
}
```
with `minor < 12` → legacy (`:474`) and `minor >= 14` → modern (`:486`), and `'legacy'`/`'latest'` aliases plus `auto` (`:496-503`).
- The version actually **changes generated output**, so it is a genuine capability tier:
  - `outbound_providers` only on ≥1.12 (`SingboxConfigBuilder.js:41-47`, `:88-90`);
  - rule-set download shape switches to `http_clients` + `route.default_http_client` on 1.14 vs `download_detour` below (`:541-564`);
  - the fix in this very commit targets the 1.14 tier (`:566-588`).
  - `createApp.jsx:93` picks a different base config: `let baseConfig = singboxConfigVersion === '1.11' ? SING_BOX_CONFIG_V1_11 : SING_BOX_CONFIG;`

### (b) Target kernel version — Clash/mihomo: no
- Grep for `1.18` / `1.19` / mihomo version handling in `src/` → **no hits**. The only capability signal is a **User-Agent substring sniff** (`ClashConfigBuilder.js:18-41`):
```js
function supportsMrsFormat(userAgent) {
    if (!userAgent) return true; // Default to mrs for unknown clients
    const ua = userAgent.toLowerCase();
    if (ua.includes('mihomo') || ua.includes('meta') || ua.includes('clash-verge') || ua.includes('stash') || ua.includes('verge')) {
        return true;
    }
    if (ua.includes('merlin') ||
        ua.includes('clashforwindows') ||
        ua.includes('clashforandroid') ||
        ua.includes('clash/')) {         // 老版本Clash核心 (Clash/v1.x.x)
        return false;
    }
    return true;
}
```
- This influences **only the rule-provider file format** (MRS vs YAML, `ClashConfigBuilder.js:668-671`). It has **zero** effect on proxy fields: no mihomo-version gate ever guards `reality-opts`, `xhttp-opts`, `anytls`, `smux`, etc. (`grep 'mihomo' src/` → only the UA string above and a comment at `:13`).

### (c) Target kernel version — Surge: no
- `SurgeConfigBuilder` has no version parameter at all; its constructor takes `(inputString, selectedRules, customRules, baseConfig, lang, userAgent, groupByCountry, includeAutoSelect)` (`SurgeConfigBuilder.js:8`). Grep `version` in that file → **no hits**.

### (d) Runtime validation that the kernel accepts the output: NO
- No schema validator: grep for `ajv|zod|joi|schema` in `src/` → **no hits** (the only `validate*` hits are unrelated).
- No kernel binary invocation anywhere: no `sing-box check`, no `mihomo -t`, no generated-config round-trip parse. CI (`.github/workflows/test.yml`) never downloads a kernel; `scripts/` contains only `release.sh`, `setup-kv.cjs`, `build-vercel.mjs`.
- What exists instead is **internal consistency checking only** — it validates that *references and group membership* are coherent, never that fields are kernel-legal:
  - `ClashConfigBuilder.validateProxyGroups()` (`:643-661`) — throws `InvalidConfigError` if a `url-test`/`fallback` group has no members; docstring says the intent is "empty groups make Clash reject the whole config, so we should fail fast".
  - `ClashConfigBuilder.sanitizeClashProxyGroups()` (`src/builders/helpers/clashConfigUtils.js:60-92`) — drops group member names not present in `proxies`.
  - `SingboxConfigBuilder.validateOutbounds()` (`:476-509`) — fills/strips empty `urltest` groups.
  - `SingboxConfigBuilder.sanitizeLegacySpecialOutbounds()` (`:511-532`) — removes legacy `block`/`dns` outbounds.
- Serialization is likewise unvalidated: Clash is `yaml.dump` of a hand-built object; sing-box is `c.json(builder.config)`; Surge is string concatenation.

### (e) "Unknown capability" vs "unsupported": NO — the two are indistinguishable
There is no enum, allowlist, or capability matrix for **values**. Unrecognised values are silently coerced, defaulted, or passed through:
- **Transport type**: forwarded verbatim with no allowlist — `src/utils.js:312-321`:
```js
export function createTransportConfig(params) {
	return {
		type: params.type,
		path: params.path ?? undefined,
		...(params.host && { 'headers': { 'host': params.host } }),
		...(params.type === 'grpc' && {
			service_name: params.serviceName ?? undefined,
		})
	};
}
```
(`type=xhttp&mode=packet-up` → `{type:'xhttp'}`; the `mode` is never read. **[RAN]** confirmed.)
- **Cipher/method**: passed through with **no cipher allowlist anywhere** (grep `aes-128-gcm|chacha20|allowedCipher|CIPHERS` in `src/` → **no hits**); `shadowsocksParser.js:121-126` and `convertYamlProxyToObject.js:17` just take the string. An unknown cipher reaches the output unchecked.
- **Security**: any non-`none` value enables TLS; only the exact string `reality` adds Reality (`src/utils.js:291-307`). So `security=xtls`, `security=garbage`, and `security=tls` are treated identically — an unrecognised security mode silently becomes plain TLS.
- **Booleans**: `parseBool` returns its `fallback` (`undefined` by default) for anything unparseable (`src/utils.js:324-331`):
```js
export function parseBool(value, fallback = undefined) {
	if (value === undefined || value === null) return fallback;
	if (typeof value === 'boolean') return value;
	const lowered = String(value).toLowerCase();
	if (lowered === 'true' || lowered === '1') return true;
	if (lowered === 'false' || lowered === '0') return false;
	return fallback;
}
```
`udp=yes` therefore becomes *absent*, not an error.
- **Config-file node types**: an unrecognised `type` is treated exactly like a known-but-unsupported one — `return null` → filtered out (Q4.5).
- **sing-box version string**: an unparseable `singbox_version` silently falls back to the UA or `'1.12'` (`createApp.jsx:494-514`); an out-of-range one silently maps to the nearest tier — e.g. `9.9` satisfies `isSingboxModernConfig` (`major !== 1 → major > 1`) and becomes `'1.14'`.
- There is also **no capability table** describing which fields each target supports; that knowledge exists only as `if/switch` arms inside each builder and as prose comments (e.g. `vlessParser.js:17`).

---

## UNKNOWN / NOT VERIFIED

1. **Kernel-side acceptance of the generated configs — UNVERIFIED.** No sing-box / mihomo / Surge binary was available or run. Claims of the form "sing-box would reject X" are **not** made by me; where the code makes such a claim I have quoted it as the code's own comment (`SingboxConfigBuilder.js:152`) and flagged it as unverified. Specifically unverified: whether sing-box accepts `transport.type: "xhttp"`, and whether it rejects the leaked `plugin` / `plugin_opts` / `tcp_fast_open` keys.
2. **Whether mihomo accepts `network: xhttp` without `xhttp-opts`** — unverified; the observable fact is only that the path/host are absent from the emitted config.
3. **Whether the deployed `sublink.works` service behaves differently from this commit** — not knowable from the clone. External docs (`README.md` links to `https://sublink.works/guide/...`, `.../api/`, `.../guide/faq/`) were **not fetched**; no online known-limitations page could therefore be checked. Only in-repo docs were searched.
4. **The full runtime surface** — I did not exhaustively read `src/runtime/*`, `src/adapters/kv/*`, `src/services/*`, the Hono JSX UI (`src/components/*`, `src/app/createApp.jsx` beyond the route handlers), or `src/config/ruleGenerators.js`. Field-loss conclusions cover the parser + builder path (Q1–Q4, Q6); a UI that renders a loss warning elsewhere cannot be fully excluded, though the i18n grep (Q4.6) found no such string and the routes emit no diagnostics channel.
5. **`test/` files were surveyed by structure, greps and targeted reads — not read line-by-line in full** (5,023 lines / 38 files). Assertions listed are ones I read directly. A round-trip assertion expressed without the words `round-trip`/`reparse`/`fidelity` could conceivably have been missed.
6. **`git log` history was not mined.** No attempt was made to find *when* a field's handling was removed (e.g. the commented-out `utls` block in `utils.js:296-299`), so intent behind those removals is unknown.
7. **The `hy2` `up`/`down` typing observation** — **[RAN]** showed `up=100` (a URI string) forwarded into sing-box output as `up_mbps: "100"` (string, not number), because `parseMaybeNumber` is applied only to the `upmbps`/`downmbps` alias (`hysteria2Parser.js:43-44`) and never to `up`/`down`. Whether sing-box accepts a string here is **unverified**; recorded as an observation, not a defect claim.
8. **`GET /xray` semantics for real Xray clients** — the handler returns Base64 of the raw URI lines (a share-link list, not an Xray JSON config). I did not verify whether any client consumes that as an "Xray target"; I only verified what the code emits.
9. **Number of `.git`-excluded files / submodules** — none found, but I did not run `git submodule status`; the working tree appears complete (no `node_modules`).
