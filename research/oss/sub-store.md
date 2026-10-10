# OSS 源码级调研：Sub-Store（`sub-store-org/Sub-Store`）

> Phase 1.5 —— 为 `proxy-node-compat` 的「节点能力识别与兼容性判断层」收集**源码级**证据。
>
> 核心问题不是"它支持多少协议"，而是：**当一个目标格式表达不了某个能力时，它到底做了什么？**
> 因为本项目的第一原则是「绝不静默丢失能力」，所以我们要找的正是**静默丢失的实现方式**，
> 作为反面证据与设计警示。Sub-Store 在这一维度上比 subconverter 走得更远
> （它有 `_extra_unsupported` 这类显式 sidecar），但**最终产物层面依然是静默丢弃**。

## 调研方法与可复现性

| 项目 | 仓库 | 调研对象（commit） | commit 日期 | 后端版本 |
|---|---|---|---|---|
| Sub-Store | `sub-store-org/Sub-Store` (JS) | `a3e61061e50b40e5c5938969aab915d05d8d7069` | 2026-10-06 | `2.42.3`（`backend/package.json`） |

方法：
1. GitHub API 文件树 + `git clone --depth 1` 取**完整源码树**（仓库已从旧版"单文件前端为主"重构为 `backend/src/**` 的模块化后端，**README 完全无法反映现状**）。
2. `grep` / 逐段 `read` 通读真实实现，所有结论附 `path:line`。
3. **实际运行代码取证**：`cd backend && npm i` 后，用 `node -r @babel/register` 直接调用
   `ProxyUtils.parse / produce / process`，对 18 组节点做端到端实验（E1–E18）。
   运行环境 `node v22.23.2`。实验脚本为临时文件、已删除，但结果在本文中以 `> 实测 E<n>` 形式引用。

**图例**：`✅` 代码证实存在 · `❌` 代码证实不存在（负证据，本项目最关键的一类） · `⚠️` 部分/有陷阱 · `❓` UNKNOWN

---

## 0. 我实际读了哪些文件

以下文件被逐段通读（不是 grep 一眼）：

| 文件 | 行数 | 为什么读它 |
|---|---|---|
| `backend/src/core/proxy-utils/index.js` | 1209 | 解析入口 `parse`、归一化 `lastParse`、产出入口 `produce`、operator 管线 `processFn` |
| `backend/src/core/proxy-utils/parsers/index.js` | 3198 | 全部 URI 解析器 + Clash/Surge/Loon/QX 行解析器 + `_extra_unsupported` 采集逻辑 |
| `backend/src/core/proxy-utils/preprocessors/index.js` | 204 | base64/SSD/Clash YAML/HTML 预处理 |
| `backend/src/core/proxy-utils/processors/index.js` | 1838 | operator 注册表、Filter/Operator 执行语义、脚本沙箱契约 |
| `backend/src/core/proxy-utils/producers/index.js` | 56 | 目标平台字符串 → producer 的映射表 |
| `backend/src/core/proxy-utils/producers/uri.js` | 1624 | 反向 URI 生成（round-trip 唯一出口） |
| `backend/src/core/proxy-utils/producers/sing-box.js` | 1702 | "目标表达不了"的最完整案例 |
| `backend/src/core/proxy-utils/producers/surge.js` | 1357 | 类型化不支持错误 `SurgeUnsupportedProxyError` |
| `backend/src/core/proxy-utils/producers/surgemac.js` | 272 | 不支持错误的兜底/降级策略 |
| `backend/src/core/proxy-utils/producers/clashmeta.js` | 507 | mihomo 白名单过滤 + "版本"判断（实为插件版本） |
| `backend/src/core/proxy-utils/producers/clash.js` | 224 | Clash（非 Meta）白名单过滤：零日志丢弃 |
| `backend/src/core/proxy-utils/producers/loon.js` / `qx.js` / `stash.js` / `shadowrocket.js` / `surfboard.js` / `egern.js` / `v2ray.js` | 844/731/364/324/405/896/24 | 各目标产出的实现与降级点 |
| `backend/src/core/proxy-utils/producers/utils.js` | 207 | `Result` 构造器、`isPresent`、`produceProxyListOutput` |
| `backend/src/core/proxy-utils/validators/index.js` | **0** | ❌ **空文件**——"validators" 目录存在但没有任何校验层 |
| `backend/src/core/proxy-utils/xhttp-utils.js` / `transport-path.js` / `ech-utils.js` / `vmess-security.js` | 149/164/149/86 | 字段级归一化辅助（含 `_`-前缀元数据约定） |
| `backend/src/restful/sync.js`（节选 240–270、478–500、800、1004）、`restful/download.js`（节选 270–295、605）、`restful/node-info.js`（全文） | — | 真实调用 `produce()` 的链路与 `delete-underscore-fields` 的启用点 |
| `backend/src/test/proxy-parsers/v2ray-and-platforms.spec.js`（节选 `_extra_unsupported` 相关 20+ 断言） | — | 官方测试固化的**预期保留/丢弃**行为 |

未读：前端仓库（不在本 monorepo 内）、`peggy/*.js` 语法文件的逐条产生式、`rule-utils/**`（分流规则，与本次问题无关）。

---

## 1. 数据模型：内部怎么表示一个节点

### 结论：**是。Sub-Store 把一切归一到 Clash/Mihomo 风格的扁平 JSON 对象**，且**没有 schema**。

节点就是一个**普通 JS 对象字面量**，字段命名刻意对齐 mihomo 的 `proxies:` YAML schema
（`type` / `name` / `server` / `port` + `tls` / `network` / `ws-opts` / `grpc-opts` /
`h2-opts` / `http-opts` / `xhttp-opts` / `reality-opts` / `plugin-opts` / `ech-opts`）。

**证据 1 — 解析器直接产出该形状**（`parsers/index.js:1843-1852`，VLESS/VMess 共用）：

```js
const proxy = {
    type: protocol, name, server, port, uuid,
    udp: true,
};
const params = {};
for (const addon of addons.split('&')) { ... params[key] = decodeURIComponent(value.join('=')); }
```

**证据 2 — 单一归一化漏斗 `lastParse()`**（`core/proxy-utils/index.js:756` 起，约 440 行）。
**所有**解析器（URI / Clash YAML / Surge 行 / Loon 行 / QX 行）的产物都必须穿过它。它做的是
"把各家方言强行掰成 mihomo 语义"，例如：

| 归一化动作 | 位置 |
|---|---|
| 所有 `*-opts` key 及其子 key 转小写 | `index.js:759-783` |
| `udp` 缺省置 `true` | `index.js:793-795` |
| `vmess`/`vless`/`trojan` 的 `network` 缺省补 `tcp` | `index.js:941-957` |
| `trojan/tuic/hysteria/hysteria2/juicity/anytls/trusttunnel/h2-connect/naive/masque/shadowquic` **强制 `tls=true`** | `index.js:968-984` |
| `shadow-tls-opts` ↔ mihomo 的 `plugin: shadow-tls` + `plugin-opts` 双向改写 | `index.js:855-905` |
| `tls` 且无 `sni` 时，从传输层 `Host` 或 `server` 推断 `sni` | `index.js:1042-1060` |
| `ws-opts.path` 缺省补 `'/'`；`h2-opts.host` 统一成数组 | `index.js:1140-1147`、`index.js:993-1011` |
| `packet-encoding` 由 `xudp`/`packet-addr` 推导 | `index.js:959-966` |
| `ports`（端口跳跃）统一成逗号分隔字符串 | `index.js:1062-1067` |

**证据 3 — "能力"全部寄生在字符串 key 上，没有枚举、没有 tagged union。**
`proxy.type` 是裸字符串；`proxy.network` 是裸字符串；`proxy.cipher` 是裸字符串。
`validators/index.js` 是 **0 字节的空文件**（❌ 无校验/无 schema 层）。

### 1.1 第二套字段：`_` 前缀 sidecar（**这是 Sub-Store 最值得注意的设计**）

因为"一切归一到 mihomo"必然丢信息，Sub-Store 用 **`_` 前缀字段**在同一个对象里挂"mihomo 表达不了的元数据"。
全仓库出现的 sidecar（grep `_extra_unsupported|_mode|_pqv|...`）：

| sidecar 字段 | 语义 | 写入位置 | 读出位置 |
|---|---|---|---|
| `_extra` | VLESS `extra=` 的**原始/用户显式覆盖**值 | `parsers/index.js:2043`（非 xhttp）、`:2075`（xhttp 且 JSON 解析失败的原始串） | `producers/uri.js:522-529`（最高优先级） |
| `_extra_unsupported` | xhttp `extra` 中**mihomo 无法结构化建模**的字段 | `parsers/index.js:2090` | `producers/uri.js:539-557` |
| `_mode` | 非 xhttp 传输的 `mode` | `parsers/index.js:2093` | `producers/uri.js` |
| `_pqv` / `_finalmask` | Xray 新版参数 | `parsers/index.js:2104`、`:2109-2113` | `producers/uri.js` |
| `_h2` / `_vcn` / `_echConfigList` | Xray 侧 h2/证书名/ECH 原始形态 | `parsers/index.js`（VLESS 段） | `producers/uri.js:596-620` |
| `_resolved` | 产出前把 `resolved` 复制一份（保留原始域名信息） | `core/proxy-utils/index.js:539` | — |
| `_dns_server` / `_domain_resolver` | sing-box 专用 | 脚本/operator | `producers/sing-box.js:30-48` |
| `_subName` / `_desc` / `_category` | 订阅级元数据 | 各层 | `core/proxy-utils/index.js:628-634` |
| `_loon_tls_profile` | Loon TLS 指纹档位 | Loon 解析器 | `lastParse` `index.js:784-792` |

**关键设计（不是随手起的名字）**：`_` 前缀同时承担两个职责——
(a) 标记"这是 Sub-Store 内部元数据，不是 mihomo 字段"；
(b) 作为**统一剥离开关**：输出到 mihomo 配置时可一键删除（见 §7）。

---

## 2. URI 解析：入口、scheme、未知参数

### 2.1 入口

| 层 | 位置 | 作用 |
|---|---|---|
| 预处理 | `core/proxy-utils/index.js:51-63`（`preprocess`）+ `preprocessors/index.js:187-194`（注册表） | 按序试 `HTML`→`Clash YAML`→`Base64`→`SSD`→`FullConfig`→`Fallback Base64`，命中即返回 |
| 主循环 | `core/proxy-utils/index.js:65-137`（`parse`） | **逐行**解析；先试"上一行成功的 parser"（热点优化，`:74-85`），失败再遍历注册表 |
| 注册表 | `parsers/index.js:3150-3197` | 49 个 parser 的**有序数组** |
| 失败处理 | `core/proxy-utils/index.js:104-106` | ❌ `$.error('Failed to parse line: ...')` 后**该行被丢弃**（节点直接消失，产物里无任何痕迹） |

### 2.2 支持的 scheme（URI 形态，全部 `✅`）

| scheme | 位置 |
|---|---|
| `socks5+tls://` `socks5://` `http://` `https://` | `parsers/index.js:157` |
| `socks://` | `:202` |
| `ss://` / `ssr://` | `:244` / `:553` |
| `vmess://`（V2rayN JSON / Shadowrocket / QuantumultX 三形态） | `:624` |
| `vless://` | `:917` |
| `anytls://` | `:2124` |
| `hysteria2://` `hy2://` | `:2181` |
| `hysteria://` `hy://` | `:2291` |
| `tuic://` | `:2362` |
| `wireguard://` `wg://` | `:2420` |
| `trojan://` | `:2519` |

非 URI 输入：Clash YAML（`:2543`）、Surge 配置行（`:2918-3144`）、Loon 配置行（`:2710-2816`）、
QuantumultX 配置行（`:2629-2708`），后三者的语法用 **Peggy 语法文件** 解析
（`parsers/peggy/{surge,loon,qx,trojan-uri}.js`）。

**❌ 没有 URI 解析器的类型**（只能从 Clash/Surge/Loon/QX 配置行进来）：
`ssh` / `snell` / `direct` / `external` / `trusttunnel` / `masque` / `h2-connect` / `tailscale` / `juicity` / `naive` / `shadowquic`。

> 实测 E8：`h2-connect://user:pass@example.com:443#h2c` →
> 日志 `ERROR: Failed to parse line: ...`，`parse()` 返回 `[]`。**节点凭空消失。**

### 2.3 未知 query 参数怎么处理 —— **同一份代码里有三种互不一致的行为** ⚠️⚠️

**(a) 主流：静默丢弃。** `vless`/`vmess`/`trojan`/`ss`/`wireguard` 等把 query 收进自由字典 `params`
（`parsers/index.js:1849-1854`），然后**只读已知 key**；字典里剩下的键**既不报警也不保留**，
函数返回后随 `params` 一起被 GC。

> 实测 E1：`vless://...&totally_unknown_param=HELLO&anotherX=1#n1`
> → 节点里**不存在**这两个 key；`produce(...,'uri')`、`produce(...,'clashmeta')`、`produce(...,'sing-box')`
> 三者的产物里都**没有任何痕迹**。`grep` 也证实 vless 段无 catch-all（`Object.keys(proxy).includes` 只出现在 3 处，见下）。

**(b) 例外：未知参数**泄漏成节点字段**（3 处）。**
`anytls` / `hysteria2` / `tuic` 三个解析器用的是**白名单 + 兜底写入**：

```js
// parsers/index.js:2165-2166  (anytls)
// parsers/index.js:2338-2339  (hysteria2)
// parsers/index.js:2407-2408  (tuic)
} else if (!Object.keys(proxy).includes(key)) {
    proxy[key] = value;
}
```

> 实测 E12/E15：`anytls://pass@example.com:443?sni=a.com&zzz=3#a1` → 节点里出现 `"zzz": "3"`；
> `tuic://...&evil2=xx#t1` → 节点里出现 `"evil2": "xx"`。
> **并且这两个字段会原样进入 `clashmeta` 产物**（实测 E15 输出含 `"evilField": "1"`）。
> 即：URI 里一个攻击者可控的查询参数，会被**注入到 mihomo 配置的 proxy 对象里**。
> 对比 (a)，同样是"未知参数"，行为完全不同——这是实现不一致，不是设计。

**(c) 报错的只有极少数**：`params.plugin` 未知（`:487` `Unsupported plugin option`）、
QX vmess `obfs` 未知（`:681` `Unsupported obfs`）——都是 throw，然后整行被丢弃。

---

## 3. Produce：目标格式与实现文件

入口 `ProxyUtils.produce(proxies, targetPlatform, type, opts)` —— `core/proxy-utils/index.js:424-640`。
映射表在 `producers/index.js:29-56`（**目标标识符是一堆大小写不一的字符串别名**）。

| 目标平台（别名） | 实现文件 | 输出模式 | 备注 |
|---|---|---|---|
| `Clash` | `producers/clash.js` | `ALL` | Clash 原版（**无 Reality/XTLS**），白名单最窄 |
| `meta` `clashmeta` `clash.meta` `Clash.Meta` `ClashMeta` `mihomo` `Mihomo` | `producers/clashmeta.js` | `ALL` | 能力最全 |
| `stash` `Stash` | `producers/stash.js` | `ALL` | |
| `Loon` | `producers/loon.js` | SINGLE（无 `type` 字段） | |
| `surge` `Surge` | `producers/surge.js` | SINGLE | 类型化 `SurgeUnsupportedProxyError` |
| `SurgeMac` | `producers/surgemac.js` | SINGLE | 包一层 Surge + mihomo external 兜底 |
| `qx` `QX` `QuantumultX` | `producers/qx.js` | SINGLE | |
| `shadowrocket` `Shadowrocket` `ShadowRocket` | `producers/shadowrocket.js` | `ALL` | |
| `surfboard` `Surfboard` | `producers/surfboard.js` | SINGLE | |
| `singbox` `sing-box` | `producers/sing-box.js` | `ALL` | **先跑一遍 ClashMeta_Producer**（见 §4.4） |
| `egern` `Egern` | `producers/egern.js` | `ALL` | |
| `uri` `URI` | `producers/uri.js` | `SINGLE` | 反向 URI（§6） |
| `v2` `v2ray` `V2Ray` | `producers/v2ray.js` | `ALL` | **基64(换行拼接的 URI)**，复用 `uri.js`（`v2ray.js:9-21`） |
| `json` `JSON` | `producers/index.js:17-23` 内联 | `ALL` | 直接 `JSON.stringify` 内部对象（**未脱敏、未过滤**） |

`type` 参数二值：`'internal'`（返回 JS 对象/数组，不序列化）vs 其它（返回字符串/文本行）。

---

## 4. 目标表达不了某个能力时，到底做了什么（**最重要**）

### 结论：**共有 6 种机制，其中 5 种最终都是"节点从产物里消失，信息只进服务端日志"。**

`produce()` 的返回值**只有配置文本/对象本身，没有任何"损失元数据"通道**
（`index.js:424-640` 全程只 `return list / producer.produce(...)`）。所以无论内部记录得多详细，
**订阅产物里看不到任何"少了什么"的提示**。

### 4.1 机制 A：产出前的白名单过滤（❌ 无产物痕迹）

```js
// core/proxy-utils/index.js:432-450
proxies = proxies.filter((proxy) => {
    const includeUnsupportedProxy = opts['include-unsupported-proxy'];
    if (!includeUnsupportedProxy && proxy.supported && proxy.supported[targetPlatform] === false) return false;
    ...
```

- `proxy.supported` 这个 hook **全仓库只被读、从不被写**（`grep -rn "\.supported" backend/src` 仅命中 `index.js:439-440`；
  测试里也 0 命中）。❌ **死接口**——前端也许曾经填它，但后端此刻没有任何代码产生它。
- 各 producer 自己还有一层白名单，例如 Clash 原版：

```js
// producers/clash.js:20-57
const list = proxies.filter((proxy) => {
    if (opts['include-unsupported-proxy']) return true;
    if (!['ss','ssr','vmess','vless','socks5','http','snell','trojan','wireguard'].includes(proxy.type)
        || (proxy.type === 'ss' && ![/* 15 种 cipher */].includes(proxy.cipher))
        || (proxy.type === 'snell' && proxy.version >= 4)
        || (proxy.type === 'vless' && (typeof proxy.flow !== 'undefined' || proxy['reality-opts']))) {
        return false;                                  // ← clash.js:57：没有任何日志
    } else if (['ws'].includes(proxy.network) && proxy['ws-opts']?.['v2ray-http-upgrade']) {
        return false;                                  // ← clash.js:62：没有任何日志
    } else if (proxy['underlying-proxy'] || proxy['dialer-proxy']) {
        $.error(`Clash 不支持前置代理字段. 已过滤节点 ${proxy.name}`);   // ← clash.js:64-67：有日志
        return false;
    }
```

> ⚠️ **同一个 filter 里三种不同程度的信息披露**：`vless+reality` 对 Clash 原版是**零日志静默消失**，
> 而 `dialer-proxy` 有明确 `$.error`。**连日志都不是一致的**，谈不上结构化。

### 4.2 机制 B：producer 抛错 → 通用捕获 → 空串 → 被过滤（❌ 无产物痕迹，有日志）

SINGLE 模式产出的统一包装（`core/proxy-utils/index.js:585-598`）：

```js
let list = proxies.map((proxy) => {
    try { return producer.produce(proxy, type, opts); }
    catch (err) {
        $.error(`Cannot produce proxy: ${proxy.name}\nReason: ${err}`);
        return '';                       // ← 变成空串
    }
}).filter((line) => line.length > 0);   // ← 空串被丢掉，节点消失
```

Surge 把"目标表达不了"专门建模成一个类型化错误（**这是全仓库最好的一个设计**）：

```js
// producers/surge.js:8-16
export class SurgeUnsupportedProxyError extends Error { ... }
function unsupported(message) { return new SurgeUnsupportedProxyError(message); }
// surge.js:1349-1351
} else if (['tcp'].includes(proxy.network) && proxy['reality-opts']) {
    throw unsupported(`reality is unsupported`);
// surge.js:224-226
throw unsupported(`Platform Surge does not support proxy type: ${proxy.type}`);
```

SurgeMac 再把它升级成"可行动的信息 + 替代方案"（`producers/surgemac.js:20-47`）：

```js
if (opts.useMihomoExternal && e instanceof SurgeUnsupportedProxyError) {
    const output = mihomo(proxy, type, opts) || '';   // 退化成 mihomo External Proxy Program
    if (!output) throw e;
    $.log(`${proxy.name} is not supported on ${targetPlatform}, try to use mihomo ... instead`);
    return output;
}
if (e instanceof SurgeUnsupportedProxyError) {
    throw new Error(`${e.message}. Surge for macOS 可手动指定链接参数 target=SurgeMac ...`);
}
```

> 实测 E9：`trojan://...&security=reality&pbk=...&fp=chrome#tr`
> - `produce(...,'surge')` → `[]`，日志 `Cannot produce proxy: tr / Reason: SurgeUnsupportedProxyError: reality is unsupported`
> - `produce(...,'SurgeMac')` → `[]`，日志带上替代方案提示

### 4.3 机制 C：ALL 模式 producer 内部 catch 后**截断列表**（❌ 无产物痕迹）

```js
// producers/sing-box.js:1392-1417（入口）
const produce = (proxies, type, opts = {}) => {
    const list = [];
    ...
    ClashMeta_Producer()
        .produce(proxies, 'internal', { 'include-unsupported-proxy': true })   // ← :1414-1416
        .map((proxy) => {
            const listStart = list.length;
            try {
                ...
                if (['xhttp'].includes(proxy.network))
                    throw new Error(`Platform sing-box does not support network: ${proxy.network}`);  // :1488-1491
                switch (proxy.type) {
                    case 'ss': if (proxy.plugin === 'shadow-tls') { ... }
                               else list.push(ssParser(proxy)); break;
                    case 'ssr': if (opts['include-unsupported-proxy']) list.push(ssrParser(proxy));
                                else throw new Error(`Platform sing-box does not support proxy type: ${proxy.type}`); break;  // :1545-1555
                    case 'vless': if (proxy.encryption && proxy.encryption !== 'none') throw new Error(`VLESS encryption is not supported`);
                                  if (!proxy.flow || proxy.flow === 'xtls-rprx-vision') list.push(vlessParser(proxy));
                                  else throw new Error(`... does not support proxy type: ${proxy.type} with flow ${proxy.flow}`); break;
                    ...
                    default: throw new Error(`Platform sing-box does not support proxy type: ${proxy.type}`);  // :1663-1666
                }
            } catch (e) {
                list.length = listStart;        // :1680  ← 把这次尝试加入的全部 outbound 回滚
                $.error(e.message ?? e);        // :1681  ← 只有一个服务端日志
            }
        });
```

`sing-box.js:1488-1666` 实质上就是一张**用 `throw` 写的、扁平的、没有返回值的 capability 表**：
sing-box 不能表达的每一种组合（xhttp 传输、ssr、vless 非 vision flow、vless encryption、TUIC v4、
shadow-tls 与 reality/h2/vision 的组合、shadow-tls 版本 ∉ {1,2,3}、naive + insecure …）都在这里
**抛错 → 截断 → 只剩日志**。

> 实测 E4：VLESS xhttp 节点 `produce(...,'sing-box','JSON')`
> → `{"outbounds": [], "endpoints": []}`，日志 `ERROR: Platform sing-box does not support network: xhttp`。
> **订阅下下来之后，用户看不到这个节点，也看不到任何注释说它被丢了。**

⚠️ 注意 `sing-box.js:1414-1416`：sing-box 的产出**先把整个列表过一遍 `ClashMeta_Producer`**
（带 `include-unsupported-proxy: true` 以躲开 mihomo 自身的过滤）。也就是说 sing-box 的能力判断
建立在"mihomo 归一化"之上（`index.js` 里也留了注释说明这一点）。**没有独立的内核模型，只有一连串转换。**

### 4.4 机制 D：`include-unsupported-proxy` —— 从"丢弃"变成"**静默降级**"（⚠️ 最危险）

这个开关是 Sub-Store 唯一的"用户可见的损失决策"入口，但它的语义是**改写配置**而不是**报告损失**：

```js
// producers/surge.js:1343-1346
if (includeUnsupportedProxy && ['http'].includes(proxy.network)) {
    $.info(`Include Unsupported Proxy: network ${proxy.network} -> tcp`);   // 只有 INFO 日志
}
```

`clash.js:22` / `clashmeta.js:57` 里 `if (opts['include-unsupported-proxy']) return true;`
则直接把白名单**整体旁路**——任何节点都会被"尽力"写成 mihomo YAML，
至于 mihomo 认不认（例如 §4.1 里的 `vless+reality` 对 Clash 原版）**不做任何校验**。

> 这正是本项目 `docs/00-design-principles.md` 原则 1 明令禁止的形态：
> **把"表达不了"变成"改一个更弱的配置然后说成功"。**

### 4.5 机制 E：SINGLE producer **没有 default 分支** → 零诊断丢弃（❌❌）

URI producer 的 `produce` 以 `let result = '';`（`producers/uri.js:803`）开头，
`switch (proxy.type)` 只有 12 个 case（`:832-1620`），**没有 `default`**。
于是任何它不认识的类型都返回 `''` → 被 `index.js:598` 的 `.filter(line => line.length > 0)` 丢掉。

> 实测 E18：Clash YAML 里一个 `type: masque` 的节点
> → `produce(proxies,'uri','internal')` 返回 `[]`，**日志里一个字都没有**（对比 E4 至少还有 ERROR）。
> 同一个节点 `produce(...,'clashmeta')` 是**正常输出**的。

### 4.6 机制 F：字段级静默丢失（⚠️ 连日志都没有，最隐蔽）

即使节点本身能产出，**节点内部的某个能力**也可能被某个 producer 悄悄不写出去。
最典型的是 hysteria2 的 `tls-fingerprint`（URI 的 `pinSHA256`）：

> 实测 E14：`hysteria2://pass@example.com:443?sni=a.com&pinSHA256=deadbeef&mport=1000-2000#hy3`
>
> | 目标 | 产物 | `deadbeef` 在不在 | 有日志吗 |
> |---|---|---|---|
> | `clashmeta` | `... "fingerprint": "deadbeef"` | ✅ 在 | — |
> | `sing-box` | `[]`（节点整体被丢） | — | ERROR: invalid SHA-256 certificate fingerprint |
> | `Loon` | `hy3=Hysteria2,...,tls-name=a.com,skip-cert-verify=false,fast-open=false,udp=true` | ❌ **不在** | ❌ 无 |
> | `surge` | `hy3=hysteria2,...,port-hopping="1000-2000",sni="a.com",...` | ❌ **不在** | ❌ 无 |
> | `uri`（回环） | `hysteria2://pass@example.com:443?sni=a.com&mport=1000-2000#hy3` | ❌ **不在** | ❌ 无 |

同样的字段级静默丢失还有一例（Loon 对 SS 插件）：

> 实测 E13：`ss://...?plugin=v2ray-plugin;tls;host=a.com;path=/ws;mode=websocket;mux=1`
> → `clashmeta` ✅ 结构化保留；`Loon` → `[]`（抛错，有日志）；
> `sing-box` → `plugin_opts: "mode=websocket;host=a.com;path=/ws;tls;sni=undefined;skip-cert-verify=false;mux=1"`
> —— ⚠️ **字符串化了，并且写出了字面量 `sni=undefined`**（`producers/sing-box.js` 的 plugin_opts 拼装）。

### 4.7 「版本」维度：有，但**不是内核版本** ❌

`clashmeta.js:463-475` 有一个叫 `isSupportedMihomoVersion(version, supportedVersions)` 的函数，
看起来很像我们要的"内核版本门槛"，**但它比的是 `proxy.version`**：

```js
// producers/clashmeta.js:463-475
function isSupportedMihomoVersion(version, supportedVersions) {
    if (version == null) return true;
    ...
    return Number.isInteger(parsed) && supportedVersions.includes(parsed);
}
// :81   snell 版本 ∈ {1,2,3,4,5}
// :94   shadow-tls 版本 ∈ {1,2,3}（ss/snell）/ {0,1,2,3}（其它）
// :108   xhttp download-settings 里的 shadow-tls 版本 ∈ {0,1,2,3}
```

`version` 的来源是 **Snell 协议版本 / ShadowTLS 插件版本**，与 mihomo 内核版本毫无关系。

**❌ 全仓库没有任何"目标内核版本"概念**：`grep -rn "mihomo.*version\|clash.*version\|MihomoVersion"` 无命中；
`produce(proxies, targetPlatform, ...)` 的 `targetPlatform` 只是 §3 表格里那串字符串别名，
**没有 `{kernel, version}` 结构**。

### 4.8 唯一一个"我真的存不下这个能力"的显式建模：`_extra_unsupported`

上述 A–F 都是"丢"，但 `_extra_unsupported` 是**反例**，且带官方注释说明设计意图：

```js
// parsers/index.js:2078-2090
// IMPORTANT: for VLESS xhttp we only keep URI extra fields that
// Mihomo does not model structurally in `_extra_unsupported`.
// Supported fields must round-trip through the structured node
// so later edits are reflected on export, while unsupported
// fields still survive VLESS URI -> node -> VLESS URI flows.
const unsupportedExtra = collectUnsupportedRootXhttpExtra(extra, { parsedDownloadSettings: downloadSettings });
if (unsupportedExtra) {
    proxy._extra_unsupported = unsupportedExtra;
}
```

采集逻辑（`parsers/index.js:1087-1226`）逐字段判断"这个字段 mihomo 能不能结构化建模"：
能 → 写进 `xhttp-opts` 的结构化字段（`applyXhttpExtraFields`，`:1566-1660`）；
不能/类型非法 → 塞进 `unsupportedExtra`。例如 `xPaddingBytes` 必须是严格正数区间，
否则进 sidecar（`:1117-1128`）；`noGRPCHeader` 必须恰好是 `true`，否则进 sidecar（`:1106-1116`）。

导出侧（`producers/uri.js:520-557`）再把它合并回 URI 的 `extra=`：

```js
function buildVlessExtra(proxy) {
    const explicitExtraOverride = serializeUriJsonValue(proxy._extra);
    if (explicitExtraOverride != null) return explicitExtraOverride;   // 用户显式覆盖优先
    if (proxy.network !== 'xhttp') return proxy._extra || '';
    const structuredExtra = buildStructuredVlessExtraObject(proxy);
    const mergedExtra = mergeUnsupportedXhttpExtraObject(structuredExtra, proxy._extra_unsupported);
    return Object.keys(mergedExtra).length > 0 ? JSON.stringify(mergedExtra) : '';
}
```

> 实测 E2：`vless://...&type=xhttp&path=%2Fxyz&mode=auto&extra={"xPaddingBytes":"100-1000","noGRPCHeader":true,"uplinkChunkSize":"not-a-range","someFutureField":{"a":[1,2]}}`
> → 节点里 `xhttp-opts` 拿到结构化的 `no-grpc-header/x-padding-bytes`，
> `_extra_unsupported` 拿到 `{uplinkChunkSize:"not-a-range", someFutureField:{a:[1,2]}}`；
> → 回环 URI **四个字段一个不少**（`extra=%7B%22noGRPCHeader%22%3Atrue%2C...%22someFutureField%22...%7D`）。
> ✅ **这是全仓库唯一做到"不静默丢失"的路径，而且范围只覆盖 VLESS xhttp 的 `extra`。**

### 4.9 汇总表

| 机制 | 位置 | 产物里有痕迹吗 | 日志级别 | 节点还在吗 |
|---|---|---|---|---|
| A 白名单过滤（Clash/Mihomo/Surge 部分） | `clash.js:20-67`、`clashmeta.js:57-165` | ❌ | `$.error`，**个别 case 无日志** | ❌ 消失 |
| B 抛错 + 通用捕获 | `index.js:585-598`、`surge.js:8-16` | ❌ | `$.error` | ❌ 消失 |
| C ALL-producer 内部截断 | `sing-box.js:1678-1681` | ❌ | `$.error` | ❌ 消失 |
| D `include-unsupported-proxy` 降级 | `surge.js:1343-1346`、`clash.js:22` | ⚠️ 产物变了但看不出降级 | `$.info` | ✅ 还在（更弱） |
| E 无 `default` 分支 | `uri.js:803 + 832-1620` | ❌ | **无** | ❌ 消失 |
| F 字段级静默丢弃 | `loon.js`/`surge.js`/`uri.js` 各 hysteria2 分支 | ❌ | **无** | ✅ 还在（少字段） |
| G `_extra_unsupported` sidecar | `parsers/index.js:2090` → `uri.js:539-557` | ✅ 完整回环 | — | ✅ 完整 |

---

## 5. Operator / 脚本管线

### 5.1 设计

Operator = **可序列化的数据**：`{ type: string, args: object, disabled?: bool, customName?: string }`。
注册表是一张 `字符串 → 工厂函数` 的表（`processors/index.js:1582-1602`，16 个）：

```js
export default {
    'Useless Filter': UselessFilter, 'Region Filter': RegionFilter, 'Regex Filter': RegexFilter,
    'Type Filter': TypeFilter, 'Script Filter': ScriptFilter, 'Conditional Filter': ConditionalFilter,
    'Quick Setting Operator': QuickSettingOperator, 'Flag Operator': FlagOperator,
    'Sort Operator': SortOperator, 'Regex Sort Operator': RegexSortOperator,
    'Regex Rename Operator': RegexRenameOperator, 'Regex Delete Operator': RegexDeleteOperator,
    'Script Operator': ScriptOperator,
    [ADD_PROXIES_FROM_SUBSCRIPTION_OPERATOR]: AddProxiesFromSubscriptionOperator,
    [RESPONSE_TRANSFORMER]: ResponseTransformer,
    'Handle Duplicate Operator': HandleDuplicateOperator,
    'Resolve Domain Operator': ResolveDomainOperator,
};
```

执行链 `processFn`（`core/proxy-utils/index.js:138-231`）的语义细节值得抄：

| 行为 | 位置 | 意义 |
|---|---|---|
| 响应修改器在节点管线里被**跳过并记日志** | `index.js:154-166` | 两类 operator 共用一张注册表，按类型分流 |
| `context.process = {type:'enable'|'disable', customNames:[...]}` 动态开关 | `index.js:113-131` | **运行时按上下文裁剪管线** |
| `item.disabled` 跳过 | `index.js:181-190` | 管线是数据，可被 UI 逐条开关 |
| **未知 operator 类型 → `$.error` + continue（不 fatal）** | `index.js:194-197` | 前向兼容：新配置落到旧实例上不会炸 |
| 每个 operator 执行前**深拷贝**输入 | `processors/index.js:1676` | operator 之间无副作用传染 |
| 两种脚本契约：函数式 `func(proxies)` 与逐节点 `nodeFunc`（`$server` 循环变量） | `processors/index.js:447-475`、`:477-512` | 见下 |
| 脚本来源：内联 / 远程 URL / 本地文件 / Sub-Store 模块 | `index.js:236-345` | 可复用的脚本分发 |

脚本沙箱契约（`processors/index.js:1752-1838`）注入的是**显式参数表**而不是全局：
`$arguments, $options, $substore, lodash, ProxyUtils, yaml, Buffer, b64d, b64e, DOMAIN_RESOLVERS,
scriptResourceCache, flowUtils, produceArtifact, require`。

逐节点契约由 `nodeFunc` 动态包一层（`processors/index.js:496-503`）：

```js
let proxies = input
let list = []
for await (let $server of proxies) {
    ${script}
    list.push($server)
}
return list
```

### 5.2 对我们「可扩展 feature registry」的借鉴价值

**有价值的（形态层面）**：
- `字符串 key → 纯函数` 的注册表 + **数据化管线**（配置里就是数组），使"处理步骤"可增删、可开关、可前向兼容。我们的 Capability Registry 完全可以同构：`capability_id → 判定函数`，判定规则全部是数据。
- **单项失败不污染整条链**：未知/失败的 operator 只影响自己，不 fatal。反过来，我们的兼容性判定也应是"每个 capability 独立出一个 verdict"。
- **显式参数注入**而非隐式全局，便于对单个 capability 判定器做单元测试。

**价值有限的（语义层面）**：
- Operator 是**变换**（transform），不是**事实**（fact）。它的输出是"改过的节点列表"，没有 reason/evidence/confidence 的概念，也没有"我不知道"这个返回值。
- 它的"扩展"靠的是**用户写 JS**（`Script Operator` 里可以对节点做任意事，包括删字段）。这对我们反而是**输入不可信**的一个来源：见 §7 里 `evilField` 能被写进 mihomo 配置的实测。

---

## 6. Round-trip：节点 → URI

### 6.1 有，在这里

| 出口 | 位置 | 形态 |
|---|---|---|
| `produce(proxies,'uri','internal')` | `producers/uri.js:800-1622`（`type='SINGLE'`） | 每个节点一条分享 URI |
| `produce(proxies,'v2ray')` | `producers/v2ray.js:9-21` | `Base64.encode(uri列表.join('\n'))` |
| 单节点分享链接 API | `restful/node-info.js:15` `producer.URI.produce(proxy)` | 前端「节点信息」面板用 |

`uri.js` 覆盖 12 个类型（`switch (proxy.type)`，`:832-1620`）：`socks5 / ss / ssr / vmess / vless /
trojan / hysteria2 / hysteria / tuic / anytls / wireguard`。**没有 `default`。**

### 6.2 会丢什么

| 丢的东西 | 证据 | 严重度 |
|---|---|---|
| **URI 里本来就未知的 query 参数** | §2.3(a) 解析期已丢 | 导入即损失，无法恢复 |
| **`_` 前缀 sidecar 字段（除 `_extra`/`_extra_unsupported`）** | `uri.js:1584/1446/1383` 显式 `!/^_/i.test(key)` 跳过 | 设计如此 |
| **任意非 `_` 的自定义字段** | 实测 E10：`Script Operator` 加的 `customTag` → `clashmeta` ✅ 有、`uri` ❌ 无 | ⚠️ 只有 JSON/Clash 出口能带走 |
| **hysteria2 的 `tls-fingerprint`（`pinSHA256`）** | 实测 E14：回环 URI 里消失 | ⚠️ 静默 |
| **`tls` 布尔在 `tuic/hysteria/hysteria2/juicity/trusttunnel` 上被显式删除** | `uri.js:507-516` `delete proxy.tls` | 设计如此（URI 里 TLS 隐含） |
| **`subName/collectionName/id/resolved/no-resolve/ip-cidr/ipv6-cidr`** | `uri.js:804-810` 显式 delete | 设计如此 |
| **值恰好为 `null` 的字段** | `uri.js:811-815` 全量 `delete` | 设计如此 |

**唯一被认真对待的回环**：VLESS xhttp 的 `extra`（`_extra` ⊃ `_extra_unsupported` ⊃ 结构化字段），
`uri.js:520-557`。**其余协议没有对应的"回环保险"。**

### 6.3 幂等性

Sub-Store 的测试（`backend/src/test/proxy-parsers/*.spec.js`、`proxy-producers/*.spec.js`）是
**手写期望值的单元测试**，我逐段看了 `v2ray-and-platforms.spec.js` 里 20+ 条 `expect(proxy._extra_unsupported).to.deep.equal(...)`。
❌ **没有 parse→produce→parse 的属性测试/fuzz**，也没有"丢了多少字段"的断言。

---

## 7. 未知 / 自定义字段能不能活下来

### 结论：**取决于它长什么样，规则写在代码里而不是 schema 里。**

**(a) 非 `_` 前缀的任意字段：能活到 Clash/JSON 产物里。**
模型是无 schema 的普通对象，`clashmeta.js` 的 map 阶段**只改名/删已知冲突字段**，不做白名单。

> 实测 E16：Clash YAML 输入带 `arbitraryUnknownKey: {nested:[1,2,3]}`
> → `produce(...,'clashmeta')` 原样输出该字段。
> 实测 E10：Script Operator 写入 `customTag` → `produce(...,'clashmeta')` 原样输出。

⚠️ **这是能力，也是注入面**：结合 §2.3(b)，`anytls://...?evilField=1` 的未知参数会被写进 mihomo 配置。
Sub-Store 自己的模型无法区分"用户有意扩展"和"URI 里塞进来的垃圾"。

**(b) `_` 前缀字段：按模式/开关被剥离。**

```js
// producers/clash.js:203-213        —— 非 internal 输出即剥离
if (type !== 'internal') {
    for (const key in proxy) if (proxy[key] == null || /^_/i.test(key)) delete proxy[key];
    deleteHttpUpgradeEarlyDataMetadata(proxy[`${proxy.network}-opts`]);
}
// producers/clashmeta.js:425-435   —— 非 internal 或显式开启 delete-underscore-fields 时剥离
if (type !== 'internal' || opts['delete-underscore-fields']) { /* 同上 */ }
```

同样的 `/^_/i` 剥离出现在 `egern.js:679`、`shadowrocket.js:294`、`stash.js:344`；
`uri.js:1383/1446/1584` 用 `!/^_/i.test(key)` 决定是否把字段写进 URI 的 query。

**谁开启 `delete-underscore-fields`**：产出 mihomo 配置文件的路径都开了
（`restful/sync.js:249-252`、`:260-263`），因为 `_h2`、`_vcn`、`_resolved` 这些不是合法 mihomo 字段。

**(c) `internal` 模式则全部保留**——这就是前端能可视化编辑 `_extra_unsupported` 的前提。

> 实测 E3：`p[0].myCustomField = {hello:'world'}; p[0]._mySidecar = 42;`
> → `produce(...,'clashmeta','internal')` 两个都在 → `produce(...,'uri')` 两个都不在。

---

## 8. 值得借鉴

### 8.1 ⭐ `_extra_unsupported` 的"结构化优先 + sidecar 兜底"协议（最有价值的一条）

代码在 `parsers/index.js:2078-2090`（注释即设计文档）+ `producers/uri.js:539-557`（消费）。
它的规则可以**逐字搬到我们的 Node Profile**：

1. 目标内核**能**结构化表达的字段 → 必须写进结构化模型，**不允许**塞 sidecar
   （否则用户改了结构化字段、sidecar 里的旧值会覆盖它 —— 注释里明确写了这个理由）。
2. 目标内核**不能**表达的字段 → 进一个**具名 sidecar**，并在导出时合并回去。
3. 用户**显式**给了原始串（`_extra`）→ 完全绕过结构化重建，尊重用户输入。

我们的对应物：`NodeProfile.features[*]` 是结构化事实，`unknown_residue` 是 sidecar，
而"导出/展示时把 residue 一起带上"就是"绝不静默丢失"的具体实现。
**Sub-Store 证明了这条路可行，也证明了它必须被显式写进去否则一定会丢。**

### 8.2 ⭐ 类型化的"目标表达不了"错误

`SurgeUnsupportedProxyError` + `unsupported()` 工厂（`surge.js:8-16`），
配合 `surgemac.js:20-47` 把它升级为"可行动的信息 + 替代方案"。
这个分层正好对应我们想要的：**"目标不支持"是一类可判定的、带 reason 的正常结果，不是异常**。
Sub-Store 走到了"给它一个专门的 Error 类"，再往前一步就是我们的 `verdict + reason_code`。

### 8.3⭐ 报错文案里带全上下文

`clashmeta.js:60-63`：`mihomo does not support HTTP/2 CONNECT proxy type. Proxy ${proxy.name} has been filtered.`
—— 目标 + 能力 + 节点名 + 处置结果，四个要素齐全。我们的 `reason` 文案应该照这个标准写。

### 8.4 数据化管线 + 前向兼容

见 §5.1：注册表是字符串 key、管线是数据数组、未知 key 只报错不致命、每步深拷贝。
我们的 Capability Registry 若要做成可扩展的，这套"数据化 + 单项失败隔离 + 未知项降级"是成熟范式。

### 8.5 `include-unsupported-proxy` 这个**显式开关**的存在本身

虽然它的语义（降级）我们不该抄，但"是否需要表达不了的节点"这件事**必须是用户显式选择**，
而不是库的隐式行为——这个产品直觉是对的。

---

## 9. 不能照搬

### 9.1 ❌ 损失只进日志，产物里零痕迹（**直接违反本项目原则 1**）

`produce()` 的签名是 `(proxies, platform, type, opts) → string | object[]`（`index.js:424`），
**没有第三个返回值、没有 error channel、没有注释行**。六种丢弃机制里有四种最终都是
"节点从产物里消失 + 服务端 `$.error`"（§4.9）。用户拿到订阅文件时**无法知道少了什么**。
我们必须在**结果对象**里带 loss，而不是在日志里带 loss。

### 9.2 ❌ 连日志都是不一致的：存在**零诊断丢弃**路径

- `clash.js:57`（whitelist 不匹配）、`clash.js:62`（ws + v2ray-http-upgrade）：`return false`，**无任何日志**。
- `uri.js:803 + 832-1620`（无 `default` 分支）：返回 `''`，**无任何日志**，实测 E18 输出 `[]` 全静默。

同一个仓库里，`dialer-proxy` 有 `$.error`，`vless+reality` 对 Clash 原版却没有——
**依赖开发者手写日志 = 一定会有遗漏**。我们的 verdict 必须是**结构性的、无法被忘记的**。

### 9.3 ❌ `include-unsupported-proxy` 式的静默降级

`surge.js:1343-1346` 把 `network: http` 悄悄改写成 `tcp` 并只打 `$.info`。
产物"看起来成功了"，实际节点的能力被削弱。**这是我们明令禁止的形态**
（`docs/00-design-principles.md` 原则 1）。要做也只能是 `SUPPORTED_WITH_LOSS` + 明确 reason。

### 9.4 ❌ 目标标识符是一串大小写不一的字符串别名，且**没有版本维度**

`producers/index.js:29-56`：`meta / clashmeta / clash.meta / Clash.Meta / ClashMeta / mihomo / Mihomo`
指向同一个 producer；`singbox / sing-box`；`qx / QX / QuantumultX`。
`isSupportedMihomoVersion` 的名字极具误导性——它比的是 Snell/ShadowTLS **插件**版本
（`clashmeta.js:463-475`、`:81/:94/:108`），**没有任何内核版本概念**（§4.7）。

我们要的是结构化的 `{ kernel: 'mihomo', version: '1.19.2' }` + 每能力独立的 `min_version`。
**不能把"内核身份"退化成字符串。**

### 9.5 ❌ 无 schema 的字段透传 + 不一致的未知参数处理

模型是无校验对象（`validators/index.js` 0 字节），导致：
- `anytls`/`hysteria2`/`tuic` 的未知 query 参数**泄漏**为节点字段并进入产物（`parsers/index.js:2165/2338/2407`，实测 E15）；
- Clash YAML 的任意未知 key 原样透传到 mihomo 输出（实测 E16）。

这不是"保留未知能力"，而是**凭空发明能力**。我们的模型必须对每个字段有明确归属：
`known & modeled` / `known & target-unsupported` / `unknown & preserved` / `invalid`。

### 9.6 ❌ 读而不写的 `proxy.supported` 死接口

`index.js:439-440` 读 `proxy.supported[targetPlatform] === false`，
但**全仓库无一处写入**。这种"预留接口没人填"的形态，正是我们要避免的：
Capability/support 数据必须是**唯一真源**，并且要有测试断言它非空、且覆盖所有已知能力。

### 9.7 ❌ 能力知识散落在 producer 的 `if/switch` 里

`sing-box.js:1488-1666` 是一张 180 行的 `throw` 表；`clash.js:20-57` 是一张 30 行的
`includes()` 白名单；`clashmeta.js:57-165` 又是一张。**同一份"sing-box 支持什么"的知识
如果要在别处复用（例如我们的 compat 层），只能靠人去读三份代码并保持一致。**
我们应该把这些抽成数据（Capability Registry），代码只负责消费。

---

## 10. 它没覆盖而我们需要的能力

| # | 缺口 | 证据 / 现状 | 对我们的要求 |
|---|---|---|---|
| 1 | **目标内核版本维度** | ❌ 全仓库无内核版本（§4.7）；`isSupportedMihomoVersion` 实为插件版本（`clashmeta.js:463-475`） | 必须有 `{kernel, version}` + 每能力 `min_version` / `max_version` |
| 2 | **机器可读的损失报告** | ❌ `produce()` 只返回文本（`index.js:424-640`），丢弃信息只有 `$.error` 日志 | `verdict` + `reason_code` + `lost_features[]` + `preserved[]` |
| 3 | **三类"不支持"的区分** | ⚠️ 只对 VLESS xhttp 有 `_extra_unsupported`（`parsers/index.js:2090`）；其余一律"目标不支持 → 丢" | 必须区分：`URI 表达不了` / `内核表达不了` / `我们还不认识` |
| 4 | **`UNKNOWN` 结果** | ❌ producer 遇到未知类型只有 `throw`（`sing-box.js:1663-1666`）或静默 `''`（`uri.js:803`） | 未知 → `UNKNOWN` 并送人工复核，**不允许猜** |
| 5 | **round-trip 不变量测试** | ❌ 只有手写期望的单测（`backend/src/test/**`），无 parse→produce→parse 属性测试 | 对每个能力建立回环断言，丢失必须显式失败 |
| 6 | **非主流客户端的节点类型** | ❌ `h2-connect`/`masque`/`trusttunnel`/`ssh`/`snell`/`direct`/`shadowquic`/`juicity` 既无 URI 解析器（§2.2），URI 导出也无 case（§4.5） | 至少要能"识别并报告存在"，即使无法导出 |
| 7 | **字段级能力的可解释性** | ⚠️ 字段被丢时无任何标记（实测 E14 `tls-fingerprint`） | 每个被丢弃的字段都要能回答"谁丢的、为什么" |
| 8 | **证据/来源可追溯** | ❌ 所有支持性判断都是硬编码 `if`，无出处（文档/源码/实测）标注 | Registry 每条能力带 `source`（官方文档/源码/内核实测） |

---

## UNKNOWN

1. **`proxy.supported` 由谁写入**：本仓库内 ❌ 无写入点（`§4.1`）。Sub-Store 的前端不在这个 monorepo 里
   （仓库已重构为纯 backend；`backend/dist/` 是空目录 + `.gitkeep`），
   前端是否会在 `Script Operator` / 数据文件里填 `supported`，**未验证**。
2. **`_extra_unsupported` 是否已扩展到其它协议**：grep 全仓库只有 VLESS xhttp 一个写入点
   （`parsers/index.js:2090`）和一个读出点（`producers/uri.js:549`）。
   但该 commit 之后是否新增、以及是否有分支/未合并 PR 在做同样的事，**未验证**。
3. **`include-unsupported-proxy` 在每个 producer 里的完整语义**：我只逐段确认了
   `surge.js:1343-1346`、`clash.js:22`、`clashmeta.js:57`、`sing-box.js:1545-1555/1699-1712` 的用法；
   `loon.js` / `qx.js` / `egern.js` / `surfboard.js` / `stash.js` / `shadowrocket.js` 里该开关的**全部分支未穷举**。
4. **Peggy 语法文件的覆盖度**：`parsers/peggy/{surge,loon,qx,trojan-uri}.js` 只做了粗读，
   没有逐条产生式比对"官方客户端支持的选项 vs Sub-Store 能解析的选项"，因此
   **哪些 Surge/Loon/QX 配置行选项在解析期被静默忽略**，未量化。
5. **日志之外的损失通道**：我只检查了 `restful/sync.js`（节选）与 `restful/download.js`（节选）。
   是否存在某个 REST 端点把"被过滤的节点数"回传给前端（例如某个 preview/统计接口），**未穷举**。
6. **线上部署版本与本 commit 的差异**：`backend/package.json` 版本号为 `2.42.3`，
   但实际用户跑的多是 release 打包产物（`sub-store.min.js`），
   其行为与 `master@a3e6106` 是否一致，**未验证**。
7. **实测覆盖度**：18 组实验（E1–E18）覆盖了 vless/vmess/trojan/ss/ssr/hysteria2/tuic/anytls/wireguard
   与 clashmeta/clash/sing-box/loon/surge/SurgeMac/uri 目标的主要路径，
   但 **QX / Shadowrocket / Surfboard / Stash / Egern / v2ray 六种产出的运行时行为未实测**，
   仅做了源码阅读。这六者是否存在与 sing-box 同类的"截断式丢弃"，**未验证**。
