# 三家互通 · 内核声明与格式选择（设计）

> 状态：设计已定，X 侧实现见 `xray--core`（`conf/lib/interop.py` / `conf/lib/native.py` /
> `Client/lib/interop.py` / `Client/lib/actions.sh`）。真机证据见
> `research/integration/three-way-interop-x.md`。
>
> 用户拍板的方案（原话）：
>
> > "我更倾向于服务端这边，它里面加一个自己是什么内核的。如果客户端这边一看是自己的内核，
> > 那就直接拉取。如果不是，就用普通话。"
>
> 前一句对应 **A 方案**：统一走 URI 作为「普通话」，原生格式作为**附加产出**。

---

## 0. 一句话

**服务端在它自己生成的订阅地址上声明「我是哪个内核的哪个发行版、我额外提供哪些格式、
每种格式从哪里取」；客户端读这一个地址就能单方面决定"拉原生还是拉普通话" ——
不猜 User-Agent、不做往返协商、不改任何已发出的载荷格式。**

```
服务端（X / M / SB）                     客户端（X / M / SB / 第三方）
  生成分享 ──┬─ 普通话产品: URI 列表 ────────►  任何客户端都能读（默认路径）
             ├─ 原生产品: 本内核 JSON ───────►  只有同内核同类发行版读
             └─ 声明（地址上） ───────────────►  读声明 → 决策 → 取对应产品
```

---

## 1. 声明放在哪里：三个候选逐个否掉，第四个选定

### 1.1 候选 A：订阅 HTTP 响应头 —— **不可行（冻结的公共服务发不出自定义头）**

公共服务 `proxy-share-service`（部署版本 `1.1.0`，RN `:9443`）的响应头只有一条通路：

```python
# Share-Service/src/share_service.py:416-426（部署文件 /opt/proxy-share-service/share_service.py）
def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None):
    self.send_response(code)
    self.send_header("Content-Type", ctype)
    self.send_header("Content-Length", str(len(body)))
    self.send_header("Cache-Control", "no-store")
    for k, v in (extra or {}).items():      # extra 只有 Content-Disposition 一个来源
        self.send_header(k, v)
```

`extra` 的唯一来源是 `content_disposition(rec)`（`rec["filename"]`）。也就是说 provider
**能影响的头只有 `Content-Type` 与 `Content-Disposition`**，其余一个字都插不进去。

而"把声明塞进 `Content-Type` 的参数位"（`text/plain; charset=utf-8; kernel=xray; …`）
被否掉的理由不是"做不到"，是**代价不对等**：Content-Type 是**所有**客户端都会读（并可能
据此分支）的头，为了一条我们自己才懂的声明去改它，等于把风险转嫁给第三方客户端；
Content-Disposition 是滥用（它会被浏览器当下载附件）。两条都违反"未知时选最通用的"。

> **未来通道（写进规范，暂不实现）**：如果公共服务哪一天开放 provider 自定义响应头
> （`meta.headers` 之类），同一份声明以 `X-Interop: <同一个查询串>` 发出，
> 客户端**先读头、读不到再读 URL**（两条通道同源同解析函数，不产生第二套语义）。

### 1.2 候选 B：`/meta` 端点 —— **不可行（唯一存在的 meta 端点是回环+鉴权的管理 API）**

公共服务只有这些路由（`share_service.py:24-34`、`do_GET` 在 `:768-783`）：

| 路由 | 谁能读 |
|---|---|
| `GET /share/<token>` | 公开（分享链接本身） |
| `HEAD /share/<token>` | 公开（预检，不消耗额度） |
| `GET /api/v1/health` | 公开（只有各 provider 计数） |
| `GET /api/v1/shares/<token>` | **需 Bearer + 只接受回环来源**（`_admin_ok()`，`:437-447`） |

远端客户端拿不到 `/api/v1/shares/<token>`；而 `health` 里没有任何逐条记录的信息。
X 这一侧**没有自己的公开 HTTP 端点了** —— 本地分享服务端（端口 9443，
`conf/lib/share_server.py`）已经下线，存储与生命周期全归公共服务
（`conf/share.sh:6-20` 的头部注释）。所以"另起一个 /meta 端点"= 要动冻结的公共服务
或重新引入一个 X 自己的服务端，两条都被本次纪律排除。

### 1.3 候选 C：内容里的字段 —— **不可行（改载荷格式 = 把已发出的订阅踢下线）**

载荷是 `base64(URI 列表)`（`conf/lib/share_payload.py:build_payload`），
约束写在同文件头部：

> "★ 载荷格式一字未改: base64 的订阅行。已发出去的链接、已经导入过的客户端
> 都按这个格式解析, **改格式等于把所有人踢下线**。"

把声明作为一行非 URI 文本混进 base64 内容，就要求**所有**第三方解析器都容忍它。
这个容忍度在本环境里**无法证明**（我们手上没有 v2rayN / Shadowrocket / 机场面板
的解析器，只有 M / SB / X 三家自己的客户端） —— 按项目原则（"未知一律 UNKNOWN，
不允许猜"），不能拿它当设计前提。反过来，URI 列表这一侧的损失是**已经入册**的
（`docs/uri-representation.md`：`ech` / `pqv` / `pcs` / `vcn` / `fm` 等参数
在 URI 里表达力不足），这正是"原生格式作为附加产出"要解决的问题，不需要改载荷。

### 1.4 选定：订阅 URL 自身（查询串）—— 服务端生成的订阅元数据

**声明放在服务端生成的那个分享地址的查询串里**：

```
http://<host>:9443/share/<token>?interop=1&kernel=xray&distribution=xray&version=26.3.27&formats=uri,xray&url-xray=<urlenc>
```

选它的四条理由，每条都可验证：

1. **它是服务端产出的订阅元数据。** 分享地址由服务端在创建分享时生成并交给用户
   （`conf/share.sh:share_create` 的 `url="http://$host:$port/share/$token"`），
   用户把它粘进客户端（`Client/lib/actions.sh:cmd_node_subscription`）——
   "服务端声明、客户端单方面读"，正是用户要的形态。
2. **对第三方客户端可证惰性。** 公共服务的路由先剥查询串：
   ```python
   # share_service.py:768-783
   def do_GET(self):
       path = self.path.split("?", 1)[0]      # ← 查询串在路由之前就被丢掉
       ...
       if path.startswith("/share/"):
           return self._serve_share(path[len("/share/"):])
   ```
   未知查询参数**不进**任何逻辑分支，返回内容与裸 URL 逐字节相同（真机实测见
   验收报告 §2.3）。也就是说：第三方客户端即使把带声明的地址原样拉走，拿到的
   仍是原来那份 URI 列表 —— **不存在"因为我加了声明而让谁读不了"的可能**。
3. **不改载荷、不改存储、不动公共服务。** 声明不落盘（不占 content、不占 meta 的
   语义位），公共服务的"provider 只是标签、content 是不可解析字节"这条边界没被破坏
   （`share_service.py:7-13`）。
4. **不碰 `#` 片段。** 片段被不少客户端当**显示名**用（本项目自己的
   `docs/uri-representation.md` §4 也把片段定为 vendor 载体，但那是**节点链接**的
   语境）；订阅 URL 的片段在个别客户端里会变成订阅名。查询串没有这个副作用。

> 载体是查询串、**不是**片段，这一点在实现里是硬约束：解析函数只读 query，
> 片段里的同名字段一律不认（避免两套语义）。

---

## 2. 字段定义

全部是查询参数，出现在**分享地址**上；大小写不敏感，未知参数忽略但必须留痕。

| 参数 | 必填 | 取值 | 含义 |
|---|---|---|---|
| `interop` | ✅ | 整数（当前 `1`） | **声明存在标记 + 规范版本**。缺失 = 没有声明；版本不认识 = 声明不认识 → 走普通话 |
| `kernel` | ✅ | `xray` / `sing-box` / `mihomo` | 服务端内核。词表与公共分享服务的 `provider` 命名**同一套**（`share_client.py:SHARE_PROVIDER`） |
| `distribution` | ✅ | 自由标签，例 `xray` / `xray-lx` / `sing-box` / `sing-box-lx` | **产出原生格式的那个发行版/fork**。取法与本项目已有的判定同源：`xray version` 首词小写（`Client/lib/compat2.py:136-139`），官方二进制 → `xray` |
| `version` | ➖ | 例 `26.3.27` | 服务端内核版本。**只作展示/compat 上下文，不参与格式决策**（决策不看版本区间，避免"区间外就猜"） |
| `formats` | ✅ | 逗号分隔，例 `uri,xray` | **可用格式清单**。`uri` 恒在（普通话）；其余项是**能读它的发行版标签**（= 原生格式的 provider 名） |
| `url-<fmt>` | 条件 | 百分号编码的 URL | 每种**非 `uri`** 格式的取件地址。`uri` 的地址就是主 URL 本身，不重复写 |

**为什么 `formats` 里的名字是发行版而不是"内核+格式名"**：原生产出是用**那个构建**的能力
渲染的（fork 带 `xhttp.extra`、AmneziaWG2 之类上游没有的字段），客户端能不能**无损**读它，
取决于"我是不是那个构建"。名字取发行版标签，客户端规则就退化成一句
`我的发行版标签 ∈ formats` —— 不需要再引入一套"格式名 ↔ 内核"的映射表（少一张表就少一处漂移）。

**未知字段/未知版本的处理**：`interop` 存在且版本不是 `1` → 视为"不认识"→ 普通话；
清单里不认识的 `url-*` 忽略并**打印一行**（不静默）。

---

## 3. 决策规则与回退链（客户端侧，纯函数）

```
decl = parse_declaration(订阅URL)                  # 只读 query；不做任何网络请求

if decl is None:                     -> uri      # 声明缺失
if decl.interop 不是已知版本:          -> uri      # 声明不认识
if decl.kernel 缺失 / 不是内核名:      -> uri      # 不认识
if decl.kernel != 我的 kernel:        -> uri      # 跨内核
if 我的发行版标签(真探测) 不在 formats: -> uri      # 发行版不在清单（不猜原生）
if url-<我的标签> 缺失/为空:           -> uri      # 声明了格式却没地址
否则:                                 -> native(url-<我的标签>)
```

**运行期回退链**（选 `native` 之后）：

```
取原生 → 成功且解析出 ≥1 个节点  → 用原生（零损失路径）
       → 网络失败 / 非 2xx / 空 / 解析 0 个 / 产物自检声明与主声明不一致
                                    → 退回主 URL 的 URI 列表
```

回退**必须把原因打出来**（`本次拉取: 普通话 (URI 列表) —— 原生取件失败: <原因>`）——
"不许为了看起来能用而静默降级"。同理，走原生时也要打出一行
`本次拉取: 原生 (provider=xray, 发行版=xray)`，用户能一眼看出这次拉的是哪种。

**发行版不一致 ≠ 跨内核**：内核相同、发行版不在清单时按上面的规则走 URI（保守，
"未知时选最通用的"）。这条**不**降级成"原生 + 警告"，因为原生产物可能带本构建不认识的
字段，而客户端解析器对不认识的 JSON 键是**静默忽略**的 —— 那才是真正的静默丢失。
发行版差异要不要"其实能读"，属于能力判定，需要证据才能放宽（见 §4、§6 UNKNOWN-U2）。

**不做的事**（与用户要求一致）：不读 User-Agent、不向服务端询问"我该拿哪个"、
不做任何协商；服务端不参与决策。

---

## 4. 与 compat 的分工

| | 谁回答 | 输入 | 输出 |
|---|---|---|---|
| **格式选择**（本规范） | `interop` 层（服务端声明 + 客户端决策） | 订阅地址上的声明 + 客户端自己的（内核, 发行版） | `native(url)` / `uri` + reason code |
| **能力判定** | `proxy-node-compat` | Node Profile（内核无关）+ 目标（内核/版本/发行版/平台/运行期事实） | `SUPPORTED` / `SUPPORTED_WITH_LOSS` / `UNSUPPORTED` / `UNKNOWN` + `losses[]`/`unknowns[]`/`reason_codes[]` |

边界：

* `interop` **不管**"能不能用、丢什么"。它不解释任何节点字段，只看声明。
* compat **不管**"从哪取"。它拿到的是已经被 `interop` 选定的那条产品解析出来的 Node Profile。
* 声明里的 `kernel` / `distribution` / `version` 作为**上下文**随订阅记录落盘
  （`declared_kernel` / `declared_distribution` / `declared_version`），供日志、
  面板与 compat 使用；**不允许**用它替代 compat 判定 —— 它是"服务端是谁"，
  不是"我这个内核能不能用"。
* 原生路径会带来 URI 表达力装不下的字段（`ech` / `mux` / `pinnedPeerCertSha256` …）。
  这些字段进 Node Profile 后由 compat 判定；URI 路径拿不到的那些字段，由
  `docs/uri-representation.md` 的 `uri.*` 表达力规则报成 `losses[]`。
  两条路径的**差异必须由 compat 说出来**，不能靠"反正客户端能用"糊过去。

---

## 5. X 侧的产品定义

| 产品 | 格式 | 内容 | 谁读 |
|---|---|---|---|
| **普通话**（默认路径） | `base64(URI 列表)`，`text/yaml` | 一字未改（`share_payload.build_payload`） | 任何客户端（含 M / SB / 第三方） |
| **原生** | `application/json` | Xray 客户端出站文档（见下） | 只有 `kernel=xray` 且发行版在清单的客户端 |

原生产品文档（自描述，便于客户端二次自检）：

```json
{
  "interop": 1,
  "kernel": "xray",
  "distribution": "xray",
  "version": "26.3.27",
  "source": "xray--core",
  "outbounds": [ { "tag": "…", "protocol": "vless", "settings": {…}, "streamSettings": {…} } ]
}
```

* 每个 `outbounds[]` 与 `conf/lib/nodes.py:build_share_link()` **同一份节点视图 + 同一份
  分享元数据**渲染，且**以 URI 路径为发布闸门**：`build_share_link()` 判为"不该发布"的节点
  （只绑回环又没有 nginx、REALITY 缺公钥…），原生文档里也必须没有 —— 两条产品发布的
  节点集合必须一致（门禁断言）。
* 客户端拿到的原生产物要能**读回**成与 URI 路径相同的节点模型（"零损失"的可验证口径：
  `node.py` 解析两条路径得到的节点记录逐字段相等，原生允许**多**字段，不允许少）。

---

## 6. UNKNOWN（没证据就不猜）

| # | 事项 | 为什么没结论 |
|---|---|---|
| U1 | 第三方客户端（v2rayN / Shadowrocket / 机场面板）对**带未知查询参数**的订阅 URL 是否有任何改写行为 | 本环境没有这些客户端；我们只证明"公共服务忽略查询串、返回内容逐字节相同"（服务端侧可证），客户端侧是否原样透传未逐一验证 |
| U2 | 同内核、**不同发行版**（fork）之间原生产物能否互相无损读 | 只有"fork 能力不同"的既有结论（LxBox 的 XHTTP/AmneziaWG2 上游没有），没有逐字段回环证据 → 规则保守走 URI |
| U3 | `interop` 响应头通道（§1.1 未来通道） | 公共服务暂不支持 provider 自定义头，未实现、未验证 |
| U4 | M / SB 两侧的服务端声明实现 | 本次纪律只改 X（+ compat 文档）；M / SB 的声明口径要在各自仓库落地后才能验"三家互读" |
| U5 | 原生产物的**运行期**可用性（不只是解析） | 解析层等价可以证；真连只覆盖了生产节点本身（见验收报告），不是对每个协议都跑了原生产物端到端 |

---

## 7. 参考

* 载荷与产品的生成：`xray--core/conf/lib/share_payload.py`、`conf/lib/nodes.py`
* 公共服务边界与路由：`Share-Service/src/share_service.py`（`_send` / `do_GET` / `_serve_share`）
* URI 表达力与损失：`docs/uri-representation.md`
* 内核/版本判定（发行版标签的来源）：`xray--core/Client/lib/compat2.py:112-158`
* 真机验收：`research/integration/three-way-interop-x.md`
