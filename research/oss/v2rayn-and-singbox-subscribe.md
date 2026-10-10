# OSS 源码级调研：v2rayN 与 sing-box-subscribe

> Phase 1.5 —— 为 `proxy-node-compat` 的「节点能力识别与兼容性判断层」收集**源码级**证据。
>
> 本文研究两条**架构路线**，而不是两个普通客户端：
> - **A. 多目标导出（multi-target export）**：同一个节点模型，同时面向 Xray 与 sing-box 生成，
>   它必然要在某处回答"这个节点在这个内核下行不行"。→ `2dust/v2rayN`
> - **B. 模板化生成（template-driven generation）**：用一份 JSON 模板 + 订阅算出内核配置，
>   能力映射全部散落在 parser 里。→ `Toperlock/sing-box-subscribe`
>
> 我们要找的核心不是"它们怎么转换"，而是：**当一个目标不支持某个能力时，它们到底做了什么？**
> 因为本项目第一原则是「绝不静默丢失能力」，所以**静默丢失的实现方式**就是最有价值的证据。

## 调研方法与可复现性

| 项目 | 仓库 | 语言 | 调研对象（commit） | commit 日期 |
|---|---|---|---|---|
| A | `2dust/v2rayN` | C# (.NET) | `b501efbc45bca3c465df99af7d4ec092c2f4c40f` | 2026-10-10 |
| B | `Toperlock/sing-box-subscribe` | Python | `25f9fd20d2c51420f8ef378e6d211f5937ad1caf` | 2026-09-29 |

方法：

1. `git clone --depth 1` 取完整源码树，全量 `grep` + 逐段 `read` 真实实现（**不看 README**）。
2. A 项目用 `ServiceLib/`（跨平台核心库，Windows/Desktop 两个壳共用）作为唯一事实来源。
3. B 项目**可运行**，因此额外写了两个探针脚本，**直接调用仓库真实函数**观测行为：
   - `main.parse_content(uri)` —— 真实解析入口，逐条 URI 观测"进 1 个节点、出几个"；
   - `main.combin_to_config(template, nodes)` —— 真实模板合并入口，观测模板/分组的落地形态。
   探针只 stub 了沙箱里缺失的三方包（`requests`/`chardet`/`ruamel.yaml`/`flask`），
   `main.py`、`parsers/*.py`、`tool.py` 执行的都是**仓库原代码**。
4. **本文所有"存在/不存在"的结论都附 `path:line`，可复现。** 代码无法证实的标 `UNKNOWN`，不推测。

**图例**：`✅` 代码证实存在 · `❌` 代码证实不存在（负证据，本项目最关键的一类） · `⚠️` 部分/有陷阱 · `❓` UNKNOWN

---

# A. v2rayN (`2dust/v2rayN`)

一句话模型：**一个"胖结构体"节点 + 一个内核无关的字段集合 + 三处分散的、内核级的硬编码能力检查**。
它确实在做"多目标导出"，但**能力判断只做到内核粒度（Xray / sing-box 两个名字），没做到字段粒度**——
这正是本项目要补的那一层。

## A1. 它内部怎么表示一个节点

**`ProfileItem`**，定义在 `v2rayN/ServiceLib/Models/Entities/ProfileItem.cs:4`，字段清单在 `:156-218`。
配套两个**以 JSON 字符串形式内嵌在列里**的子对象：

| 结构 | 文件 | 作用 |
|---|---|---|
| `ProfileItem` | `Models/Entities/ProfileItem.cs:156-218` | 主表：地址/端口/账号/协议/传输名/TLS 元数据 |
| `ProtocolExtraItem` | `Models/Entities/ProtocolExtraItem.cs:3-62` | 协议专属：vmess `AlterId`/`VmessSecurity`、vless `Flow`/`VlessEncryption`、ss `SsMethod`、wg `WgPublicKey`…、hy2 `Ports`/`Obfs`/`Hy2RealmUrl`、naive、MASQUE、组节点、**自定义 outbound 是否 sing-box endpoint** |
| `TransportExtraItem` | `Models/Entities/TransportExtraItem.cs:3-19` | 传输专属：`RawHeaderType`/`Host`/`Path`/`XhttpMode`/`XhttpExtra`/`GrpcAuthority`/`GrpcServiceName`/`GrpcMode`/`KcpHeaderType`/`KcpSeed`/`KcpMtu` |

设计特征（对本项目有直接借鉴意义）：

1. **扁平并集（fat struct），不是 tagged union。** 所有协议的字段平铺在同一个类里，
   靠 `ConfigType`（`Enums/EConfigType.cs:2-19`，15 个值）区分语义。`ProtocolExtra` /
   `TransportExtra` 是**后加的补丁层**：老字段保留在原地并标 `[Obsolete]`
   （`ProfileItem.cs:173-218` 共 9 个：`HeaderType`/`RequestHost`/`Path`/`Extra`/`Ports`/`AlterId`/`Flow`/`Id`/`Security`），
   取值时优先新层（`GetTransportExtra()` `:138-141`，注释明确写 "Use TransportExtra.Xxx instead"）。
   → **迁移是"加字段 + 留旧字段"，没有 schema 校验，旧字段里可能残留真相。**
2. **节点自身携带"用哪个内核"**：`public ECoreType? CoreType { get; set; }`（`ProfileItem.cs:160`）。
3. `ConfigVersion`（`ProfileItem.cs:161`）是**节点模型 schema 版本**（3→4 的迁移标记，
   `Manager/AppManager.cs:345-371`、`:448`、`:546`），**不是内核版本**——这个区分后面 A5 会用到。
4. `IndexId` 是 `[PrimaryKey]`（`:156-157`），持久化在 SQLite（`Helper/SqliteHelper.cs`）。
5. **`EConfigType.Outbound` / `Custom` 是"逃生舱"**：`IsComplex()`（`:62-65`）为真时，
   节点内容是一份**原样内核 JSON**，且对 `Outbound` 类型 **`Address` 存的是一个文件路径**
   （`Handler/Builder/CoreConfigContextBuilder.cs:344-364` 读盘）。

## A2. Xray / sing-box 切换：它怎么判断"这个节点在这个内核下不可用"

### 内核是怎么选的（两级）

```
ProfileItem.CoreType（节点级，ProfileItem.cs:160）
   ↓ 为空时
Config.CoreTypeItem：ConfigType → CoreType 的全局映射表
   （Models/Configs/ConfigItems.cs:132-138；Config.cs:35）
   ↓ 查不到时
默认 ECoreType.Xray
```
全部逻辑在 `Manager/AppManager.cs:666-675`（`GetCoreType`）。
可选内核被硬编码成两个字符串：`Global.CoreTypes = ["Xray", "sing_box"]`（`Global.cs:361-365`）。

⚠️ **全局映射表的默认值是错的**：`ViewModels/OptionSettingViewModel.cs:236-250`
为**每一个** `EConfigType` 都建了一条 `CoreType = ECoreType.Xray` 的映射——
包括 Xray 根本不支持的 `TUIC` / `Anytls` / `Naive`。这个矛盾**只在运行/导出时**才被 A2 的判断逻辑发现。

### 真正的判断逻辑：`NodeValidator`（这是全项目对本项目最重要的一段代码）

文件：`v2rayN/ServiceLib/Handler/Builder/NodeValidator.cs`

```csharp
// NodeValidator.cs:3-11 —— 结果模型：错误与警告分开，只有 Error 才叫"失败"
public record NodeValidatorResult(List<string> Errors, List<string> Warnings)
{
    public bool Success => Errors.Count == 0;
    ...
}
```

**明确的"不支持"列表**，是三个静态集合（`NodeValidator.cs:16-23`）：

```csharp
private static readonly HashSet<string> SingboxUnsupportedTransports =
    [nameof(ETransport.kcp), nameof(ETransport.xhttp)];                    // sing-box 不支持 kcp / xhttp

private static readonly HashSet<EConfigType> SingboxTransportSupportedProtocols =
    [EConfigType.VMess, EConfigType.VLESS, EConfigType.Trojan, EConfigType.Shadowsocks];
    // 只有这四种协议允许用 "非 raw" 传输；其余协议在 sing-box 下只能是 raw

private static readonly HashSet<string> SingboxShadowsocksAllowedTransports =
    [nameof(ETransport.raw), nameof(ETransport.ws)];
    // 注释在 :188 写的是 "tcp/ws/quic"，但代码里没有 quic，白名单只有 raw/ws
```

外加**协议级**白名单（`Global.cs:367-396`，注意这两个集合在字段命名上就写着 "Support"）：

| 集合 | 内容 | 位置 |
|---|---|---|
| `XraySupportConfigType` | VMess / VLESS / Shadowsocks / Trojan / Hysteria2 / WireGuard / MASQUE / SOCKS / HTTP（**无 TUIC / Anytls / Naive**） | `Global.cs:367-378` |
| `SingboxSupportConfigType` | 上面 + TUIC / Anytls / Naive（**无 v2fly 时代的 ShadowsocksR 等**，SSR 在 `EConfigType` 里本就不存在） | `Global.cs:380-394` |
| `SingboxOnlyConfigType` | 差集，仅用于 UI/路由分流提示 | `Global.cs:396` |

校验主体（`NodeValidator.cs:25-171`）的分支结构本身就是"能力矩阵"的雏形：

| 分支 | 行为 | 行号 |
|---|---|---|
| `EConfigType.Custom` | **直接 `return`，完全跳过所有校验** | `:34-37` |
| `EConfigType.Outbound` | 要求 `item.CoreType == coreType`，否则 `MsgCoreNotSupportProtocol` | `:39-46` |
| 组节点（PolicyGroup / ProxyChain） | 跳过，交给 `ValidateGroupNode` | `:48-52` |
| sing-box 分支 | `ValidateSingboxTransport()` + `SingboxSupportConfigType` | `:60-72` |
| **Xray 分支** | **只有协议级检查（`XraySupportConfigType`），没有 transport 级检查** | `:73-79` |
| 协议细节 | vmess 要求 UUID；vless 要求 UUID 且 `Flow ∈ Global.Flows`；ss 要求 method ∈ `SsSecuritiesInSingbox` | `:83-107` |
| Xray: `xtls-*` + mux | **Warning**（不是 Error）`MsgOptionsConflict` | `:109-114` |
| ws + alpn=h3/h2 且无 ECH | **Warning**（硬编码英文字符串，未走 i18n） | `:116-122` |
| TLS | `allowInsecure` 且无 `Cert`/`CertSha` → Warning | `:134-148` |
| reality | `PublicKey` 必填（Assert） | `:150-153` |
| `XhttpExtra` / `Finalmask` | 只校验"是不是合法 JSON object" | `:156-170` |

**sing-box 的 transport 级规则**（`NodeValidator.cs:173-196`，这是全项目唯一一份 transport 能力矩阵）：

```csharp
// :175-179  sing-box does not support xhttp / kcp transports
if (SingboxUnsupportedTransports.Contains(net)) return MsgCoreNotSupportNetwork(...);
// :181-186  sing-box does not support non-tcp transports for protocols other than vmess/trojan/vless/shadowsocks
if (!SingboxTransportSupportedProtocols.Contains(configType) && net != raw) return ...
// :188-193  sing-box shadowsocks only supports tcp/ws/quic transports
if (configType == Shadowsocks && !SingboxShadowsocksAllowedTransports.Contains(net)) return ...
```

三个消息模板（`ServiceLib/Resx/ResUI.resx`）：

```
MsgCoreNotSupportProtocol           = "Core '{0}' does not support protocol '{1}'"
MsgCoreNotSupportNetwork            = "Core '{0}' does not support network type '{1}'"
MsgCoreNotSupportProtocolTransport  = "Core '{0}' does not support protocol '{1}' when using transport '{2}'"
```

### 三处重复且已经漂移的检查

`NodeValidator` 不是唯一的检查点，生成服务里还有**各写一份的硬编码黑名单**：

| 位置 | 检查 | 内容 |
|---|---|---|
| `Services/CoreConfig/Singbox/CoreConfigSingboxService.cs:19-27` | `!IsValid()` → `CheckServerSettings`；`GetNetwork() is kcp or xhttp` → `Incorrectconfiguration` | 与 NodeValidator 重复 |
| `Services/CoreConfig/V2ray/CoreConfigV2rayService.cs:19-27` | `!IsValid()`；**`GetNetwork() is quic`** → `Incorrectconfiguration` | Xray 侧"不支持列表"只有 quic 一项 |

⚠️ **Xray 侧那条 `quic` 判断实际上不可达**：`ProfileItem.GetNetwork()`（`ProfileItem.cs:53-60`）在
`Network` 不在 `Global.Networks`（`Global.cs:331-339`：`raw/xhttp/kcp/grpc/ws/httpupgrade`，**没有 quic**）
时会返回 `Global.DefaultNetwork = "raw"`。所以 `Network == "quic"` 永远被规范化成 `raw`，
`GetNetwork() is quic` 恒为 false。→ **防御性检查被复制到三处之后，其中一处已经失效而没人发现。**

### 校验结果怎么被消费

| 调用点 | 行为 | 行号 |
|---|---|---|
| `Handler/Builder/CoreConfigContextBuilder.cs:342` | 单节点注册时校验 | — |
| `:58-61` | **主节点失败 → 整体中止，不生成配置** | `if (!nodeValidatorResult.Success) return ...` |
| `:85-95` | 路由规则引用的出站节点失败 → **Error 被降级成 Warning**，并把该规则改回 `Proxy` 出站 | 静默换路 |
| `:366-374` | 失败节点**不进** `AllProxiesMap`（进不了生成结果），但日志只记一行 `Logging.SaveLog` | — |
| `:489-508` | 组节点所有子节点都无效 → `MsgGroupNoValidChildNode` | — |
| `ServiceLib/Manager/NoticeManager.cs:48-64` | 逐条发到消息面板 + snack（最多 10 条） | UI 呈现 |
| `ViewModels/MainWindowViewModel.cs:702`、`ViewModels/ProfilesViewModel.cs:753,784` | 启动 / 导出配置 / 导出剪贴板前调用 | 仅 3 处 |

❌ **没有任何"列表级/导入级"的预检**：`grep -n "CoreType|NodeValidator" ViewModels/ProfilesViewModel.cs`
零命中——节点列表里**不显示**"此节点在当前内核下不可用"，也没有在切换内核时批量重算。
判断只发生在"要生成配置的那一刻"，也就是**用户点启动之后**。

## A3. 分享链接解析入口 & 不认识的参数怎么办

**入口**：`Handler/Fmt/FmtHandler.cs:35-110`（`ResolveConfig`，按 `Global.ProtocolShares`
的 scheme 前缀分发，`Global.cs:238-250`）。VLESS 走 `Handler/Fmt/VLESSFmt.cs:5-35`：

```csharp
// VLESSFmt.cs:25-32
var query = Utils.ParseQueryString(url.Query);
item.SetProtocolExtra(item.GetProtocolExtra() with {
    VlessEncryption = GetQueryValue(query, "encryption", Global.None),
    Flow            = GetQueryValue(query, "flow") });
item.StreamSecurity = GetQueryValue(query, "security");
ResolveUriQuery(query, ref item);          // ← 真正的白名单解析在 BaseFmt
```

**核心事实：query 解析是一张封闭白名单**（`Handler/Fmt/BaseFmt.cs:197-316`）。
`ResolveUriQuery` 恰好读这 **22 个键**（`grep -oE 'GetQuery(Value|Decoded)\(query, "[a-z]+"' | sort -u | wc -l` = 22）：

```
security sni alpn fp pbk sid spx pqv ech vcn pcs fm         (BaseFmt.cs:201-225)
type headerType host path seed mtu extra mode authority serviceName   (:231-306)
```

**❌ 不在这 22 个键里的参数，既不报错、不警告，也不记录——直接消失。**
全仓 `grep -niE "unknown|unrecognized|unexpected (key|param|field)"` 在
`ServiceLib/Handler/` 与 `ServiceLib/Services/` 下**零命中**（唯一命中是
`ConnectionHandler.cs:135` 的 `"unknown"` 国家码兜底）。
即：`vless://...&encryption=mlkem768x25519plus...&someNewParam=x` 会**成功导入**，
新参数无声蒸发，用户看到"导入成功"。

更隐蔽的两层静默降级：

| 输入 | 行为 | 行号 |
|---|---|---|
| `type=<不在 Global.Networks 里的值>` | **静默改成 `raw`**：`if (!Global.Networks.Contains(net)) net = raw;` | `BaseFmt.cs:236-239` |
| `type` 命中已知值但 switch 无 case | `default: item.Network = raw;` | `BaseFmt.cs:308-310` |
| 任何协议解析异常 | 抛到 `FmtHandler.ResolveConfig` 顶层 catch → `null` + `msg = Incorrectconfiguration` | `FmtHandler.cs:104-108` |

→ 第一种最危险：一个 `type=splithttp`（xhttp 的历史名）或未来新传输的链接，
**不会报错，会变成一条能导入、能启动、就是不通的 raw 节点**。这与本项目 README 里
那条 mihomo 实测（未知 transport 被静默按 tcp 处理）是**同一类失效**，只不过这次发生在 URI 解析层。

另外还有两处解析期的静默丢弃（`Common/Utils.cs:192-220`）：

- `:206-209` 没有 `=` 的 query 片段 `continue` 掉；
- `:214-217` **同名键只保留第一个**，后续同名值静默丢弃（first-wins）。

VLESS 专属的一个缺口：**`allowInsecure` 不被解析**。
`grep -rn "AllowInsecure" ServiceLib/Handler/Fmt/` 只命中
`AnytlsFmt.cs:30`、`Hysteria2Fmt.cs:169,184`、`TrojanFmt.cs:5,30`、`TuicFmt.cs:33`、`VmessFmt.cs:145`
——**`VLESSFmt.cs` / `BaseFmt.cs` 完全没有**。所以
`vless://...&allowInsecure=1` 导入后 `AllowInsecure` 为空（= 校验证书）。

## A4. 导出/分享：有没有"生成回 URI"，会不会丢字段

有，而且是**两条通道**：

### 通道 1：标准分享 URI（`BaseFmt.ToUriQuery`，`Handler/Fmt/BaseFmt.cs:20-181`）

`FmtHandler.GetShareUri`（`FmtHandler.cs:7-33`）按 `ConfigType` switch 到各 `*Fmt.ToUri`。
回写字段与解析白名单**基本对称**（`BaseFmt.cs:24-179`）：

```
security sni fp pbk sid spx pqv alpn ech vcn pcs fm
type(=raw 时写 "tcp" 别名，Global.cs:53) headerType host path
[raw] / [kcp: headerType seed mtu] / [ws|httpupgrade: host path] /
[xhttp: host path mode extra] / [grpc: authority serviceName mode]
```

评价：**对 VLESS 家族来说比大多数客户端完整**（`ech`/`pqv`/`vcn`/`pcs`/`fm` 都回写了）。
其中 `ech` 已是跨客户端事实标准，但 **`pqv`（Mldsa65Verify）/`vcn`（VerifyPeerCertByName）/
`pcs`（CertSha）/`fm`（Finalmask）是 v2rayN 私有拼写**，其它客户端不认识
→ 这正是本项目 README 四层模型里 "URI Representation" 那一层的问题：**表达得下不等于别人读得懂**。
但即便如此，仍明确丢失以下字段：

| 丢失的字段 | 理由 | 证据 |
|---|---|---|
| `Cert`（PEM 证书链） | URI 里没有对应 key（只有 `pcs`=SHA256/`vcn`=域名） | `BaseFmt.cs:20-181` 无 `Cert`；Xray 侧却要读它 `V2rayOutboundService.cs:345` |
| `MuxEnabled` | vmess JSON 体里也没有 | `VmessFmt.cs:55-73` 字段集里无 mux |
| VLESS 的 `AllowInsecure` | 见 A3，解析与回写都没有 | `BaseFmt.cs` 无 |
| `SS`/`SOCKS` 的 `AllowInsecure` | 同上 | `ShadowsocksFmt.cs`/`SocksFmt.cs` 无 |
| 节点管理字段 `ConfigVersion`/`Subid`/`DisplayLog`/`PreSocksPort` | 设计上不导出 | `BaseFmt.cs:20-181` |
| **整类节点**：`MASQUE`/`Outbound`/`Custom`/`PolicyGroup`/`ProxyChain` | `GetShareUri` 的 switch **无 case → `_ => null`** | `FmtHandler.cs:23` |

⚠️ 批量导出时上表最后一类是**静默跳过**的：

```csharp
// ViewModels/ProfilesViewModel.cs:806-811
var url = FmtHandler.GetShareUri(it);
if (url.IsNullOrEmpty()) { continue; }        // ← 不计数、不提示
...
NoticeManager.Instance.SendMessage(ResUI.BatchExportURLSuccessfully);   // ← 仍然报"成功"
```

### 通道 2：`v2rayn://` 内部格式（**全保真**，`Handler/Fmt/InnerFmt.cs`）

```csharp
// InnerFmt.cs:279-281
var jsonStr = JsonUtils.Serialize(jsonObj, false);
var encodedStr = Utils.Base64Encode(jsonStr).Replace('+','-').Replace('/','_').Replace("=","");
return $"{Global.InnerUriProtocol}{item.ConfigType.ToString().ToLower()}/{encodedStr}";
// Global.cs:70 → InnerUriProtocol = "v2rayn://"
```

它把**整个 `ProfileItem`（含 `ProtoExtra`/`TransportExtra`/自定义 outbound 内容）**序列化成
base64url JSON（`:98-281`），解析时反向还原（`:7-100`，并把 `ProtoExtraObj`/`TransportExtraObj`
摊平成字符串列，`:145-176`）。**这是唯一无损的往返通道**——代价是只有 v2rayN 自己认。
`Resolve` 会主动丢弃 `EConfigType.Custom`（`:29-33`，注释给了安全理由）。

**测试现状**：`ServiceLib.Tests/Fmt/ShareUriQueryTests.cs`（73 行）只覆盖
percent 编码、未转义 `=`、非规范 SIP002 plugin 三种编解码问题。
❌ **没有任何"字段完整性 round-trip"测试**——也就是说 `Cert`/`MuxEnabled`/`AllowInsecure`
这三类丢失，从来没有被断言过。

## A5. 有没有内核版本维度的能力判断

**❌ 没有。** 精确表述：

| 版本设施 | 存在？ | 用途 | 证据 |
|---|---|---|---|
| `SemanticVersion`（三/四段 + prerelease + build，可比较） | ✅ 完整实现 | 基础设施 | `Models/Dto/SemanticVersion.cs` |
| `CoreInfo.LockedMaxVersion` | ⚠️ 存在但**只用于下载/更新钉版本** | 让自动更新停在某个版本 | `Models/CoreConfigs/CoreInfo.cs:19`；`Services/UpdateService.cs:177-207`（`x.Version <= coreInfo.LockedMaxVersion`） |
| sing-box 的 `LockedMaxVersion` 实际取值 | ❌ **被注释掉了** | — | `Manager/CoreInfoManager.cs:232`：`//LockedMaxVersion = new SemanticVersion(1, 14, int.MaxValue),` |
| 生成侧的版本分支 | ❌ **零** | `grep -n "Version" Services/CoreConfig/{Singbox,V2ray}/` 无任何版本条件 | — |
| 运行内核版本探测 | ✅ 有（`GetCoreVersion()`） | 仅用于"是否提示升级" | `Services/UpdateService.cs:226-258`；`CoreInfo.VersionArg`（`CoreInfo.cs:23`，sing-box = `"version"`，`CoreInfoManager.cs:234`） |

**结论**：v2rayN 的能力矩阵是「**内核级**」的，没有「**内核 + 版本**」维度。
`SingboxUnsupportedTransports = {kcp, xhttp}` 是**永久硬编码**：
将来 sing-box 支持了 xhttp，v2rayN 不会自动放宽，必须改代码。
它有一个 `ConfigVersion`（节点 schema 版本，见 A1）——**它给"节点模型"做了版本，却没给"内核能力"做版本。**

## A6. 字段级静默丢失（本文最重要的一节）

`NodeValidator` 只检查 **transport（kcp/xhttp）+ 协议白名单**。
它**完全不检查"某个字段在目标内核里有没有对应物"**。而 `SingboxOutboundService` 与
`V2rayOutboundService` 对同一字段的读取是**不对称**的。逐字段 `grep` 全仓 `Services/CoreConfig/`：

| `ProfileItem` 字段（URI key） | Xray 生成 | sing-box 生成 | 后果 |
|---|---|---|---|
| `VerifyPeerCertByName`（`vcn`） | ✅ `V2rayOutboundService.cs:330` | ❌ **全仓无 sing-box 引用** | 证书域名校验静默消失 |
| `CertSha`（`pcs`） | ✅ `:361-363` → `pinnedPeerCertSha256` | ❌ 只在 `NodeValidator.cs:137` 被当作"免警告借口" | 证书 pinning 静默消失 |
| `SpiderX`（`spx`） | ✅ `:379` | ❌ 无引用 | reality spiderX 静默消失 |
| `Mldsa65Verify`（`pqv`） | ✅ `:380` | ❌ 无引用 | 后量子校验静默消失 |
| `Finalmask`（`fm`） | ✅（kcp finalmask，`:401-431`） | ❌ 无引用 | finalmask 静默消失 |
| `Cert` / `EchConfigList` / `Fingerprint` / `Alpn` | ✅ `:345` / `:329` / `:328,375` / `:327` | ✅ `SingboxOutboundService.cs:479-484` / `:496-500` / `:469-476` / `:462` | 对称 |

**这五个字段，在 sing-box 内核下被静默丢弃，且不产生任何 Error/Warning。**
用户看到的是"节点导入成功、内核正常启动、代理也通"，只是**这五项能力已经没了**。
——这是「绝不静默丢失能力」原则的**教科书级反例**，也是本项目最有说服力的一条立项证据。

同一文件里还有几处**静默归一化**（语义上安全，但同样不告知）：

| 行为 | 行号 |
|---|---|
| `flow = xtls-rprx-vision-udp443` → `xtls-rprx-vision`（sing-box 无 udp443 变体） | `SingboxOutboundService.cs:211-214` |
| ss method 不在当前内核白名单 → 写成 `"none"` | `SingboxOutboundService.cs:132-133`（`AppManager.GetShadowsocksSecurities`） |
| vmess `security` 不合法 → `Global.DefaultSecurity` | `SingboxOutboundService.cs:117-124` |
| `Network` 不在白名单 → `raw`（解析层与取用层各一次） | `ProfileItem.cs:53-60`；`BaseFmt.cs:236-239` |
| `FillOutboundTransport` 的 `default: break;`（kcp/xhttp 走这里时 transport 整个不写 = 静默降级为 raw） | `SingboxOutboundService.cs:601-603` |

最后一行值得单独标注：**生成器本身没有能力检查**。它依赖 `NodeValidator` 在前一步拦截；
一旦有人绕过校验直接调用生成器（或用 `EConfigType.Custom` 绕开——`NodeValidator.cs:34-37` 直接 return），
就会得到一份**缺 transport 的坏配置**，而不是一个错误。

## A7. 另一个静默面：去重身份比字段集窄

订阅合并用的"同一个节点"判定 `ConfigHandler.CompareProfileItem`（`Handler/ConfigHandler.cs:1294-1322`）
比较了 `Address/Port/Password/Username/Network/传输细节/Flow/Sni/Alpn/Fingerprint/Pbk/Sid/Finalmask`，
**但没有比较** `EchConfigList` / `CertSha` / `VerifyPeerCertByName` / `Mldsa65Verify` / `SpiderX` / `Cert` / `MuxEnabled`。
→ 只改了 ECH 或只改了证书 pin 的订阅更新，会被判为"同一节点"。
身份模型比字段模型窄，是**另一类不丢字段却丢能力**的路径。

## A8. v2rayN 没做的事（小结）

- ❌ **字段级能力矩阵**：只有 transport 级（且仅 sing-box 有）与协议级。
- ❌ **内核版本维度**：见 A5。
- ❌ **"未知参数"概念**：URI query 白名单之外一律静默丢弃，无 `UNKNOWN` 状态。
- ❌ **导入期/列表期预检**：判断只发生在生成配置时（A2 末）。
- ❌ **loss 概念**：全仓搜 `\b(loss|lost|dropped|silently)\b`，唯一相关的是
  `Common/Utils.cs:759-760` 的注释——而它讲的是**正则超时 fail-open，好让节点不被静默丢掉**。
  也就是说：作者**明确在意"静默丢节点"这件事**（在那一个点上），但没有把它上升成全局模型。
- ⚠️ **警告与错误分家是好设计**（`NodeValidatorResult.Errors/Warnings`），
  但 Warning 只进消息面板，不影响"能不能用"的结论，也没有"损失了什么"的结构化描述。

---

# B. sing-box-subscribe (`Toperlock/sing-box-subscribe`)

一句话模型：**一份整文件 JSON 模板 + 一组按 URI scheme 分派的 parser**。
"这个节点生成什么 outbound"**完全由 parser 决定**，模板只负责分组/路由/DNS；
不支持的能力有**四种互不一致的结局：跳过节点 / 生成坏配置 / 抛异常 / 降级直连**。

规模：Python，`main.py` 633 行 + `tool.py` 335 行 + `parsers/*.py` 15 个模块 ≈ 1700 行，
`config_template/*.json` 5 份。**可运行**，因此下列行为均为**实测**（探针脚本见文末说明）。

## B1. JSON 模板机制怎么工作

### 模板是什么

`config_template/` 下的整份 sing-box 配置骨架，**每份 = 一个内核版本 + 一种形态**：

| 模板 | 行数 | 特征 |
|---|---|---|
| `sb-config-1.12.json` | 736 | `dns.independent_cache`；`rule_set.tag` 是**字符串**；`route` 无 `default_http_client`/`find_process` |
| `sb-config-1.14.json` | 174 | 新增顶层 `services`（clash api dashboard）与 `http_clients`；`route.default_http_client`/`route.find_process`；`dns.final`/`dns.optimistic`；**`rule_set.tag` 变成数组**（一个 rule_set 供多个 tag 复用） |
| `config_template_groups_rule_set_tun*.json` | 703/738 | 带分组版 |
| `config_template_no_groups_tun_VN.json` | 159 | 无分组版 |

模板选择：`get_template()` 列出 `config_template/*.json` 按文件名排序（`main.py:30-36`），
用户在终端输序号（`:547-567`）或 CLI `--template_index`，或由
`providers.config_template` 指定一个**远程 URL**（`:591-597`，直接 `requests.get(...).json()`）。

### "这个节点该生成什么 outbound" 由谁声明

**❌ 不由模板声明。** 两段机制拼起来：

**(1) 节点 outbound：按 URI scheme 选 parser 模块生成**（`main.py:208-221`）

```python
def get_parser(node):
    proto = tool.get_protocol(node)                 # 正则 ^(.+?):// 取 scheme
    ...
    if not proto or proto not in parsers_mod.keys():
        return None                                 # ← 不认识就返回 None
    return parsers_mod[proto].parse
```

`parsers_mod` 由 `os.walk('parsers')` 动态装载（`main.py:21-27`），
即 **scheme → 模块名 → `parse()`**。所以 `vless://` 一定进 `parsers/vless.py`，
而节点 outbound 的形状是在 Python 里逐字段拼出来的，**模板完全不参与**。

**(2) 模板声明的是"分组与占位符"，最终把节点 outbound 直接追加在模板 outbounds 之后**

```python
# main.py:507-509
for group in data:
    temp_outbounds.extend(data[group])
config['outbounds'] = config_outbounds + temp_outbounds      # 模板组 + 生成节点，顺序拼接
```

模板里的组用**占位符引用 tag**：`"{all}"`、`'{' + group + '}'`（`main.py:436-449, 461-486`）。
`pro_node_template()` 把占位符解析成 **tag 列表**（`:420-423`），可选 `filter`
（include/exclude 正则，`:67-107`）决定哪些节点进哪些组，用完即删（`:505-506`）。

**实测**（`combin_to_config(sb-config-1.14, {tag_1: [HK-01(vless+reality), US-01(trojan)]})`）：

```
最终 outbounds 类型序列:
  direct, selector×17, urltest, vless, trojan
模板里的 Proxy 组 {all} 展开后: ['HongKong','United States','Singapore','Japan','Taiwan','Others','Direct']
新增节点 outbound（原样追加，未做任何改写）:
  {"tag":"HK-01","type":"vless","server":"1.1.1.1","server_port":443,"uuid":"u1",
   "tls":{"enabled":true,"server_name":"a.com","reality":{"enabled":true,"public_key":"PBK"}}}
```

→ 模板 = **配置骨架与分组策略**；parser = **节点能力映射**。两者之间只有 `tag` 一个契约。
这正是"模板化生成"路线的结构性弱点：**能力映射没有中心表，散落在 parser 的条件分支里**。

### 分组为空时的行为（重要）

```python
# main.py:489-503
if len(t_o) == 0:
    t_o.append(direct_item['tag'])      # ← 该组 outbounds 变成 ['Direct']
    print('发现 {} 出站下的节点数量为 0 ，会导致sing-box无法运行，请检查config模板是否正确。'.format(po['tag']))
```

实测输出：`发现 Taiwan/Singapore/Japan/Others 出站下的节点数量为 0 ...`。
它**打印了告警**（这点比 B 项目其它地方好），但生成结果仍然落盘：
该组变成**直连**。对一个代理工具来说，"分组里没有节点 → 改走 direct"意味着
**流量裸奔**，而不是"报错不生成"。

## B2. vless + xhttp / reality / vision / ech 的映射规则写在哪

| 能力 | 映射位置 | 结果 |
|---|---|---|
| reality（`pbk`/`sid`） | `parsers/vless.py:57-73` | ✅ `tls.reality{enabled,public_key,short_id}` + `tls.utls.enabled` |
| uTLS（`fp`） | `parsers/vless.py:66-73` | ✅ `tls.utls.fingerprint` |
| **vision（`flow`）** | `parsers/vless.py:41-43` | ⚠️ **原样透传**：`if flow and flow.lower()!='none': node['flow']=flow` |
| TLS（`security`/`sni`/`alpn`/`insecure`） | `parsers/vless.py:44-56` | ✅（`server_name`/`alpn`/`insecure`） |
| ws（含 `?ed=` 早数据） | `parsers/vless.py:79-94` | ✅ `transport.ws` + `early_data_header_name`/`max_early_data` |
| grpc | `parsers/vless.py:95-99` | ✅ `transport.grpc.service_name` |
| http（h2/http） | `parsers/vless.py:75-78` | ⚠️ 只写 `{'type':'http'}`，**host/path 不映射** |
| mux（`protocol=smux/yamux/h2mux`） | `parsers/vless.py:119-130` | ✅（`max-streams` 或 `max-connections`/`min-streams`） |
| **xhttp** | `parsers/vless.py:100-101` | ❌ **`return None  # 不支持xhttp`** |
| **ech** | — | ❌ **全仓 0 命中**（`grep -i ech` 在 parsers/ 下只命中 `tool.py` 里 emoji 正则的 `Czechia`/`Liechtenstein`） |
| `encryption`（VLESS Encryption / ML-KEM） | — | ❌ 无任何映射（`clash2base64.py` 会传 `encryption=` 出来，但 vless.py 不读） |
| `spx` / `pqv` / `vcn` / `pcs` / `fm` | — | ❌ 无映射（v2rayN 的私有 key 在这里完全不存在） |

其它 parser 的传输分支（**都没有 else**）：

| parser | 处理的 `type`/`net` | 行号 |
|---|---|---|
| `parsers/vless.py` | http / ws / grpc / xhttp(→None) | `:74-101` |
| `parsers/trojan.py` | h2 / ws / grpc | `:62-92` |
| `parsers/vmess.py` | (b64 JSON) h2·http·tcp / ws / quic / grpc | `:100-133` |
| `parsers/hysteria2.py` | 无 transport 概念；`obfs`/`upmbps`/`downmbps`/`mport`/`server_ports` | `:16-47` |
| `parsers/clash2base64.py`（Clash → 分享链接适配器） | vmess / ss / ssr / trojan / vless / tuic / hy2 / wg / http / socks / anytls | `:5-366` |

⚠️ **`flow` 原样透传是个隐患**：`xtls-rprx-vision-udp443` 会被写进 sing-box 的
`outbounds[].flow`。v2rayN 在这里是**主动归一化**的（`SingboxOutboundService.cs:211-214` 把它
映射成 `xtls-rprx-vision`），sing-box-subscribe 不归一化。
**sing-box 对这个值的具体反应（接受/忽略/报错）本文未实测 → 见 UNKNOWN #3。**

## B3. 遇到 sing-box 不支持的能力时，行为是什么（**实测**）

探针直接调用仓库真实的 `main.parse_content(text)`，逐条 URI 观测"1 个节点进、几个出"。
`parse_content` 是解析总入口（`main.py:186-205`）：

```python
nodelist = []
for t in content.splitlines():
    t = t.strip()
    if len(t) == 0: continue
    factory = get_parser(t)
    if not factory: continue                     # ← 静默跳过：无 parser 的协议
    try:
        node = factory(t)
    except Exception as e:  #节点解析失败，跳过      # ← 裸 except + pass，注释即承认
        pass
    if node:                                     # ← 注意：node 只在 try 里被绑定
        nodelist.append(node)
return nodelist
```

### 实测结果表

| # | 输入 | 实际行为 | 结局分类 | 证据 |
|---|---|---|---|---|
| 1 | `vless://…&type=xhttp&path=/xh&host=…` | 返回 `[]` | **跳过节点** | `parsers/vless.py:100-101` |
| 2 | `vless://…&type=httpupgrade&path=/up` | 返回节点，但**没有 `transport` 键** | **生成坏配置** | `parsers/vless.py:74-101` 无 `else` |
| 3 | `vless://…&type=kcp&seed=abc` | 同上，`transport` 缺失 | **生成坏配置** | 同上 |
| 4 | `vless://…&security=reality&pbk=PBK&sid=ab&fp=chrome&spx=/&ech=…&pqv=…&vcn=…` | 返回节点：reality+utls 保留，**`ech`/`spx`/`pqv`/`vcn` 消失** | **部分丢字段** | `vless.py:57-73` 是唯一读取处 |
| 5 | `vless://…&flow=xtls-rprx-vision-udp443` | `"flow":"xtls-rprx-vision-udp443"` 原样写出 | **可疑坏配置** | `vless.py:41-43` |
| 6 | `vless://…&encryption=mlkem768x25519plus.native.0rtt` | 节点正常生成，**encryption 字段不存在** | **丢字段** | 全文件无 `encryption` 读取 |
| 7 | `trojan://…&type=xhttp` | 节点正常生成，**无 `transport`** | **生成坏配置**（与 #1 不一致！） | `parsers/trojan.py:62-92` |
| 8 | `trojan://…&type=httpupgrade` | 同上 | **生成坏配置** | 同上 |
| 9 | `hysteria2://…&pinSHA256=deadbeef&ech=…` | 节点生成，`pinSHA256`/`ech` **消失** | **丢字段** | `parsers/hysteria2.py:16-47` |
| 10 | `mieru://…`（无 parser 模块） | 返回 `[]` | **跳过节点，无日志** | `main.py:219-220` |
| 11 | 畸形行 `vless://@@@:::not-a-port@@@`（**首条**） | **抛 `UnboundLocalError`** 冒泡出 `parse_content` | **崩溃** | `main.py:199-204`（`node` 只在 `try` 内绑定） |
| 12 | 好行之后再放畸形行 | 返回 `[good-node, good-node]` | **重复上一个节点** | 同上（`node` 残留旧值） |

第 11/12 条是**实测复现的真实缺陷**（不是推断）：

```
good only        -> ['good-node']
good then bad    -> ['good-node', 'good-node']       # 畸形行 → 上一行节点被复制
bad then good    -> RAISED UnboundLocalError: local variable 'node' referenced before assignment
```

第 12 条的重复节点随后会被 `tool.proDuplicateNodeName`（`tool.py:255-265`）**改名保留**
（追加 `" 2"`），于是订阅里凭空多出一个指向同一台服务器的节点；第 11 条则会让整次生成失败
（在 Flask 里变成一条与真实原因无关的 500 + "Subscription parsing timeout" 文案，
`api/app.py:281-285`）。

### 另一个入口：Clash 订阅 → 分享链接 → parser

Clash 格式的订阅不能直接进 sing-box，要走适配器 `parsers/clash2base64.py`：

- `link` 在函数开头初始化为 `''`（`:5`），**未匹配任何分支的类型返回空串**
  → 空行走 `parse_content` 的 `len(t)==0: continue` → **静默消失**。
  实测等价路径：`vless` + `network: xhttp`（ws/grpc/tcp 三分支都不匹配）→ 节点丢失。
- `vmess` + `net: httpupgrade` → vmess.py 的 h2·http·tcp/ws/quic/grpc 都不匹配 → 节点**保留**但无 transport。
- **`reality-opts` 只在 `grpc` 与 `tcp` 分支处理**（`clash2base64.py:204-221`）：
  `vless + network: ws + reality-opts` 会被当成**普通 TLS**。
- `ech-opts` 在 clash2base64.py 中 **0 命中** → Clash 里的 ECH 在第一个适配器就丢了。

### 结局分类总结

> **"同一个不支持"在这个仓库里有 4 种不同结局**：
> ① 静默跳过（vless+xhttp、未知 scheme、未知协议）
> ② 生成坏配置（trojan+xhttp、vless+kcp/httpupgrade、vmess+未知 net —— 节点还在，transport 没了 → sing-box 按默认 TCP 处理）
> ③ 崩溃/污染（畸形行 → UnboundLocalError，或复制上一行节点）
> ④ 降级直连（分组 0 节点 → 填 `Direct`，打印告警）
>
> 选择哪一种**取决于你恰好用了哪个 scheme、哪个 parser**，没有任何统一规则。

## B4. 有没有 loss / warning / skip 的结构化输出或日志

**❌ 基本没有。** 逐项核查：

| 机制 | 存在？ | 证据 |
|---|---|---|
| logging 模块 / 日志文件 | ❌ 全仓无 `import logging` | `grep -rn "logging" .` 零命中 |
| 计数器 / 统计 | ❌ 只有 1 处，且是**死代码** | `tool.removeNodes`（`tool.py:267-282`）打印"去除了 N 个重复节点"，但 `grep -rn "removeNodes"` 全仓**无调用点** |
| 结构化报告（JSON/返回体） | ❌ | Flask 只返回整份配置文本或 `{'status':'error'}`：`api/app.py:278`、`:281`、`:313-319` |
| 解析异常的记录 | ❌ **裸 `except: pass`** | `main.py:201-202`（注释：`#节点解析失败，跳过`） |
| 跳过节点的计数 | ❌ | `main.py:196-198`（无 parser）与 `:218-220`（协议被 exclude）都是裸 `continue`/`return None` |
| 订阅级的失败提示 | ⚠️ 有，但粒度是**订阅**不是节点 | `main.py:60-62`"没有在此订阅下找到节点，跳过"；`:246-250`"获取错误，跳过此订阅" |
| 分组 0 节点的告警 | ⚠️ 有 `print` + 降级 Direct | `main.py:489-503` |
| 全局协议排除 | ⚠️ 有配置项，静默生效 | `providers.json` 的 `"exclude_protocol":"ssr"` → `main.py:210-218` 直接返回 None |

对比 A 项目：v2rayN 至少有 `NodeValidatorResult.Errors/Warnings`（**结构化**）并在 UI 呈现；
sing-box-subscribe 的"报告"就是终端里的中/越双语 `print`。
**对本项目而言，它是"零可观测性"的极端样本**：用户拿到的配置里少了哪些节点、
哪些节点少了哪些能力，**在系统里不存在任何记录**。

唯一"不丢"的设计出现在相反方向：**重名节点会被自动改名保留**，而不是丢弃
（`tool.py:255-265`）。也就是说：**它在意节点数量的保全，但不在意节点能力的保全。**

## B5. 版本维度 & B 项目没做的事

- **版本意识的唯一形态 = 模板文件名**：`sb-config-1.12.json` / `sb-config-1.14.json`。
  如上表，两者差异正是 sing-box 版本间**字段的增删**：
  1.14 新增 `services`、`http_clients`、`route.default_http_client`、`route.find_process`、
  `dns.final`、`dns.optimistic`，并把 `rule_set.tag` 从字符串改成数组；
  1.12 里的 `dns.independent_cache` 属于旧 API。
- ❌ **从不读取实际 sing-box 版本**：`grep -n "version" main.py api/app.py tool.py`
  只命中 `dns_route_same_list` 里的 `"ip_version"`（`main.py:404`）。
  用户选错模板 → 配置里出现当前版本不认识的字段 → sing-box 对未知字段是**拒绝加载**
  （本项目 README 也记录过"配置校验通过但语义失效"的另一类情形，两者是不同的失败模式）。
- ❌ **能力 × 版本矩阵：没有**。xhttp 不是"1.12 不支持、1.13 支持"地建模，
  而是 `parsers/vless.py:101` 一行 `return None # 不支持xhttp` —— **永久性、无版本、无退出条件**。
- ❌ **运行时回环**：生成后不做校验（不调 `sing-box check`/`run`），没有反馈回路
  （`main.py:632` 之后只有注释掉的 `updateLocalConfig`）。
- ❌ **"未知"状态**：`get_parser` 返回 `None`、"没有对应字段"、`except: pass` 三者
  在实现上是同一个分支 —— 与前一份 OSS 调研（subconverter）观察到的模式**完全一致**。

---

# 横向结论：对我们最有价值的 3 点、最该避免的 2 点

## C1. 两者对"不可用"的处理对比

| 维度 | v2rayN（多目标导出） | sing-box-subscribe（模板化生成） |
|---|---|---|
| 节点模型 | 胖结构体 + JSON 内嵌子对象 + 9 个 Obsolete 字段 | 没有模型 —— 直接是 sing-box 的 `outbound` dict |
| 能力判断在哪 | `NodeValidator`（1 文件）+ 2 处重复检查 | 散在 15 个 parser 的 `if/elif` 里，无中心 |
| 判断粒度 | **内核 × 协议 × transport**（无字段级） | **无**（scheme × type 字符串匹配） |
| 明确"不支持"列表 | ✅ 3 个静态集合 + 2 个协议白名单 | ⚠️ 1 行注释 `# 不支持xhttp` |
| 内核版本维度 | ❌（只有下载钉版本的 `LockedMaxVersion`） | ⚠️ 文件名级模板选择，无校验 |
| 结构化输出 | ✅ `Errors` / `Warnings` + UI 呈现 | ❌ 只有 `print`（且关键路径连 print 都没有） |
| 不支持的结局 | 主节点 **Error 中止**；路由节点 **降级 Warning 换路** | 跳过 / 坏配置 / 崩溃 / 降级 Direct（**四种**） |
| 未知参数 | 静默丢弃（URI 白名单 21 key 之外） | 静默丢弃（无字段映射即不存在） |
| loss 概念 | ❌（但有 Warning 分家 + 一处 fail-open 注释） | ❌ |
| 可观测性 | 中（校验日志 + 消息面板） | **零**（`except: pass`） |
| 有无全保真通道 | ✅ `v2rayn://`（整 ProfileItem base64） | ❌（只有整份配置，没有节点级） |

## C2. 对我们最有价值的 3 点

1. **`NodeValidatorResult(Errors, Warnings)` 的形态值得抄，但它的矩阵维度必须扩展。**
   v2rayN 已经证明"错误/警告分家 + `Success = Errors.Count == 0` + 逐条人类可读消息"
   是可行的工程形态（`NodeValidator.cs:3-11`、`NoticeManager.cs:48-64`）。
   它缺的恰恰是我们要补的：把 `(item, coreType)` 扩成
   `(item, kernel, version)`，并把判断维度从「协议 / transport」下钻到「**字段 / 能力**」。
   **`SingboxUnsupportedTransports = {kcp, xhttp}` 这类集合，正是我们要数据化的那张表的第一行。**
2. **"检查点必须唯一"是被 v2rayN 亲手证明的教训。** 同一个"不支持"写三处
   （`NodeValidator.cs:16-23`、`CoreConfigSingboxService.cs:23-27`、`CoreConfigV2rayService.cs:23-27`），
   结果 Xray 侧那条 `quic` 判断**因为 `GetNetwork()` 的规范化而永久不可达**（A2）。
   我们的 Capability Registry 必须是**唯一事实来源**，生成侧不得再写第二份黑名单。
3. **模板化生成路线的正确分工：模板管"骨架/分组/路由/DNS"，能力映射管"节点字段"——
   但能力映射不能散在 parser 里。** sing-box-subscribe 用 `tag` 作为模板与节点之间唯一契约
   （`main.py:420-423`、`:507-509`），这个解耦本身是好的；
   坏的是节点侧没有中心映射表，于是每加一个传输就多一个 `elif`，
   最终出现"vless 跳过 xhttp、trojan 保留 xhttp"这种**同仓库内不一致**
   （`parsers/vless.py:100-101` vs `parsers/trojan.py:62-92`）。

## C3. 最该避免的 2 点

1. **"节点还在，能力没了"**——两个项目都栽在这里，而且形式和 v2rayN 的字段级丢失
   （A6 表：`vcn`/`pcs`/`spx`/`pqv`/`fm` 在 sing-box 路径下全无引用）比"跳过节点"危险得多。
   跳过节点只是少一条线路，**能力静默消失会给出一个"能用但降级/不安全"的节点**
   （证书 pinning 与 `verifyPeerCertByName` 消失正是安全问题）。
   本项目的 `SUPPORTED_WITH_LOSS` 必须**列出具体丢了哪些能力**，
   而不是只给一个布尔值 —— 这正是 A6 那张表存在的意义。
2. **"不认识的输入 = 默认值"**——两条路线都选择把未知值折叠成默认值：
   v2rayN 把未知 `type` 折成 `raw`（`BaseFmt.cs:236-239`）、重复 query 键取第一个
   （`Utils.cs:214-217`）；sing-box-subscribe 的 parser 缺 `else` 分支时**不写 transport**
   （`parsers/vless.py:74-101`、`trojan.py:62-92`、`vmess.py:100-133`）。
   语义上这是"最没破坏性"的选择，工程上是**最坏的**：它把
   "我不认识这个能力" 伪装成 "这个节点本来就这么简单"。
   **未知必须是 UNKNOWN 状态并上浮，绝不允许折叠成默认值。**

## C4. 仍未证实的事项（UNKNOWN 清单）

| # | UNKNOWN | 为什么没证实 | 影响 |
|---|---|---|---|
| 1 | `EConfigType.Custom` 节点在 Xray/sing-box 下的实际校验路径（`NodeValidator.cs:34-37` 直接 return 之后是否有别的兜底） | 需要跟随 `CoreConfigContextBuilder` 全部路径 + GUI 交互，本次只静态追踪了主路径 | 自定义节点可能是完全不受检的旁路 |
| 2 | v2rayN `EConfigType.Outbound` 节点的 `Address`（文件路径）在订阅导入时的安全/路径处理边界 | 只确认了 `:344-364` 的读盘与错误分支 | 与能力判断无关，但与"节点内容来源"有关 |
| 3 | sing-box 对 `flow: "xtls-rprx-vision-udp443"` 的精确反应（接受 / 忽略 / 拒绝加载） | 需要实际跑内核；本文未执行（v2rayN 主动归一化是间接证据） | 决定 sing-box-subscribe 第 5 号用例是"坏配置"还是"无效配置" |
| 4 | sing-box 对**未知顶层字段 / 未知 outbound 字段**的行为（拒绝加载 vs 忽略） | 同上，未实测内核 | 决定"选错版本的模板"的失败模式；本报告不对此下结论 |
| 5 | `sb-config-1.12.json` 与 `1.14.json` 各自对应的**最低/最高可用 sing-box 版本区间** | 模板文件名是唯一线索，仓库无版本声明、无 CI | 影响"模板 → 版本"映射表 |
| 6 | v2rayN 三个检查点（`NodeValidator` / `CoreConfigSingboxService` / `CoreConfigV2rayService`）在**全部 GUI 操作路径**上是否总是一起执行 | 静态追踪到 3 个调用点（`MainWindowViewModel.cs:702`、`ProfilesViewModel.cs:753,784`）+ 生成服务自检 | 影响"唯一检查点"结论的强度（结论本身已由重复实现证实） |

> **UNKNOWN 条数：6。**
> 其中 #3 / #4 属于"需要真内核实测"，建议直接进 `research/empirical/` 的探针用例
> （`tools/probe/cases.json` 已有同类结构）。

---

## 附：B 项目探针脚本

为让 B 部分的实测可复现，探针脚本保存在 `/tmp/oss/probe_sbs.py` 与 `/tmp/oss/probe_sbs2.py`
（不属于本仓库交付物）。核心做法：

```python
sys.modules["requests"] = <stub>; sys.modules["chardet"] = <stub>
sys.modules["ruamel.yaml"] = <stub>; sys.modules["flask"] = <stub>
sys.modules["api.app"] = <stub with TEMP_DIR>
os.chdir("/tmp/oss/sing-box-subscribe")     # init_parsers() 走相对路径 os.walk('parsers')
import main; main.init_parsers(); main.providers = {...}
main.parse_content(uri)                      # ← 仓库真实函数
main.combin_to_config(template, nodes)       # ← 仓库真实函数
```

`main.py` / `parsers/*.py` / `tool.py` 执行的是克隆下来的原代码，未做任何修改。
