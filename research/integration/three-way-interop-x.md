# 三家互通 · X 侧实施与真机验收报告

> ---
>
> ## ⚠ 部署状态更正（2026-10-11 复核）
>
> 1. 本报告原写「提交 `da5fff0` → `32f65ef` → `be4ec8e`，**已推到 `main`**」——
>    **与事实不符**。三条提交当时在本地分支 `feat/three-way-interop` 上；
>    `main` 与 `origin/main` 都还停在 `55c736a`，**一个字节都没推**。
>    （本轮复核已把它 fast-forward 合入 `main` = `be4ec8e`，仍未 push。）
> 2. §4 的"真机验证"跑在 **RN/CC 上的隔离副本**里：RN 侧是 `/tmp/tw-rn/**` 的独立
>    服务实例（`:19481` / `:19482`）与独立数据目录，CC 侧是 `/tmp/xbd-m` 的客户端副本。
>    当时 RN `/root/conf/` 里是 `55c736a` 的 50 个文件 —— `conf/lib/interop.py` 与
>    `conf/lib/native.py` **在部署路径上根本不存在**（`find /root -name interop.py`
>    当时返回空）。
>    真公共服务 `:9443`、真内核二进制、真节点确实是真件，所以结论对**代码**成立；
>    对「**已部署**」不成立。

> 3. 本轮已把仓库 HEAD 逐字节分发到 RN 并在**部署态**重跑验收 —— 见 `three-way-interop-x-deployed.md`。


> 日期：2026-10-10/11 ｜ 实施对象：`mi1314cat/xray--core`（服务端 `conf/` + 客户端 `Client/`）
> 设计依据：`docs/three-way-interop.md`（本次新增）
> 门禁：`bash tools/check_libs.sh` → **782 通过 / 0 失败**（改前基线 756/0，即 `origin/main` = `55c736a`）
> 提交：`da5fff0`（服务端）→ `32f65ef`（客户端）→ `be4ec8e`（门禁+验证台），已推到 `main`
> 真机：RN（X 服务端真实部署）+ CC（三个客户端）

---

## 0. 一句话结论

服务端在**它自己生成的订阅地址**上声明「内核 / 发行版 / 可用格式 / 每种格式从哪取」；
客户端读这一个地址就能单方面决定拉原生还是普通话，**零往返、不看 User-Agent、不改任何
已发出的载荷格式**。真机三条路径全部按设计走：同内核同发行版 → 原生 Xray JSON；
跨内核 → URI 列表；声明缺失 / 原生取件失败 → 回退 URI（并把原因打出来）。
**对角线不倒退**：CC 上旧代码与新代码都是解析 5 / 导入 5，SS2022-02 真连 **204**。

---

## 1. 声明放在哪：三个候选逐个否掉，第四个选定

用户给的三个候选，两个被**冻结的公共服务**堵死，一个会动到已发出的格式：

| 候选 | 结论 | 证据 |
|---|---|---|
| 订阅 HTTP 响应头 | **不可行** | `share_service.py:416-426` 的 `_send()` 只发 Content-Type / Content-Length / Cache-Control，`extra` 的唯一来源是 `Content-Disposition`。provider 一个自定义头都插不进去 |
| `/meta` 端点 | **不可行** | 公开路由只有 `/share/<token>`（+HEAD）、`/api/v1/health`；逐条 meta 端点是 `GET /api/v1/shares/<token>`，要求 **Bearer + 回环来源**（`_admin_ok()`，`:437-447`）。X 自己的公开 HTTP 分享服务已下线 |
| 内容里的字段 | **不选** | 载荷是 `base64(URI 列表)`，`conf/lib/share_payload.py:15` 写着"改格式等于把所有人踢下线"；而在 base64 里塞一行非 URI 文本，要求**所有**第三方解析器容忍 —— 本环境证明不了（只有 M/SB/X 三家自己的客户端），按纪律不能当前提 |

**选定：订阅 URL 的查询串**（服务端生成的"订阅元数据"本身）：

```
http://107.173.154.178:9443/share/<token>?interop=1&kernel=xray&distribution=xray
   &version=26.3.27&formats=uri,xray&url-xray=http%3A%2F%2F…%2Fshare%2F<原生 token>
```

四条理由（每条都实测过）：

1. **它是服务端产出的订阅元数据** —— 地址由服务端在创建分享时生成
   （`conf/share.sh:share_create`），客户端把它粘进来即可决策，**不需要额外请求**。
2. **对第三方客户端可证惰性** —— 公共服务路由先剥查询串：
   ```python
   # share_service.py:768-783
   def do_GET(self):
       path = self.path.split("?", 1)[0]      # ← 查询串在路由之前被丢掉
       ...
       if path.startswith("/share/"):
           return self._serve_share(path[len("/share/"):])
   ```
   实测（RN 真部署同版本服务代码）：同一 token 带声明与不带声明，响应体
   `sha256` **逐字节相同**（`2020dfb4d457e91a7ebdfb2a46303cfb6468472c634b3cd64e97a9c98369484a`）。
   也就是说第三方客户端即使原样拉走带声明的地址，拿到的仍是原来那份 URI 列表。
3. **不改载荷、不改存储、不动公共服务** —— 声明不落盘进 content，公共服务"provider 只是
   标签、content 是不可解析字节"这条边界没被破坏。
4. **不碰 `#` 片段** —— 片段在不少客户端里会被当订阅名；且"同一语义两套载体"必然漂移，
   所以实现里**只读 query**（门禁有一条断言：片段里的同名字段不算声明）。

> 未来通道（写进设计、暂不实现）：公共服务若开放 provider 自定义响应头，同一份声明以
> `X-Interop: <同一个查询串>` 发出，客户端先读头、读不到再读 URL。

---

## 2. 字段定义与决策规则（实现见 `conf/lib/interop.py`，客户端逐字节副本）

| 参数 | 必填 | 含义 |
|---|---|---|
| `interop` | ✅ | 声明存在标记 + 规范版本（`1`）。缺失 = 没有声明；版本不认识 = 声明不认识 |
| `kernel` | ✅ | `xray` / `sing-box` / `mihomo`（与公共服务的 provider 命名同一套词表） |
| `distribution` | ✅ | 产出原生格式的发行版/fork（`xray` / `xray-lx` …）。取法与本项目既有判定同源：`xray version` 首词小写 |
| `version` | ➖ | 服务端内核版本，只作展示/上下文，**不参与格式决策** |
| `formats` | ✅ | 可用格式清单，`uri` 恒在；其余项是"能读它的发行版标签" |
| `url-<fmt>` | 条件 | 每种非 `uri` 格式的取件地址（`uri` 就是主 URL 本身） |

决策（纯函数 `interop.decide`，9 条规则逐条有门禁断言）：

```
声明缺失 / 规范版本不认识 / 内核缺失或不认识 → uri
跨内核                                        → uri
本机发行版探测不出来（没内核二进制）           → uri   ← 不猜自己是官方版
本机发行版不在 formats 清单（含 fork 不一致）   → uri
声明了格式却没给地址 / 地址不是 http(s)         → uri
否则                                          → native(url-<本机发行版>)
```

**发行版不一致 → 普通话**是刻意的：fork 的原生产物可能带本构建不认识的字段，而客户端
解析器对不认识的 JSON 键是**静默忽略**的 —— 那正是"静默丢失"，不能叫零损失。

运行期回退：原生取件失败（网络 / 非 2xx / 空 / 解析 0 个节点）→ 退回主地址的 URI 列表，
**并把原因打出来**（`本次拉取: 普通话 URI 列表 —— …；原生取件失败(<url>) → 回退`）。

---

## 3. X 侧实现了什么（文件清单）

| 文件 | 内容 |
|---|---|
| `conf/lib/interop.py`（新，权威） | 声明构建 / 解析 / 决策 + 本机内核事实真探测；CLI 给 bash 调用 |
| `Client/lib/interop.py`（新，vendored） | 与上者**逐字节相同**（门禁比对 sha256）—— 字段名对不上时表现是"静默全走普通话" |
| `conf/lib/native.py`（新） | 原生产品生成器：节点视图 + 分享元数据 → Xray 客户端出站 JSON。以 `build_share_link()` 为**发布闸门**；显示名从链接读回（不另写一遍命名逻辑） |
| `conf/share.sh` | 创建时两条记录（主=普通话 base64 URI / 附带=原生 `application/json`）+ 地址上带声明；列表打印**带声明的地址**与「内容/格式」两列；刷新按 `role` 分派；停用/撤销/改次数**成对**生效 |
| `Client/lib/actions.sh` | `_sub_interop_decide` / `_sub_fetch_nodes` / `_sub_fetch_by_declaration` / `_sub_report_choice`；导入与刷新走**同一套**决策与回退；日志打出"本次拉取: 原生/普通话" |
| `Client/lib/node.py` | `parse_xray_json_many()`（多出站文档；原来订阅路径按行拆 → 一个节点都解析不出）；接进 `parse_many`/`parse_subscription`；补 `realitySettings.spiderX`（URI 路径读得到、Xray JSON 路径以前读不到） |
| `xray-panel.sh` | `_XRAY_LIB_FILES` 补两个新库 |
| `tools/interop-corpus.py`（新） | 测试语料生成器（各协议×传输×加密 + 四类边界） |
| `tools/interop-e2e.sh`（新） | 端到端验证台：真 `share.sh create` + 真分享服务代码（**独立实例/端口/数据目录**）+ 真 `xbd node sub` |
| `tools/check_libs.sh` | 新增"三家互通"断言组（26 条） |

原生产品长这样（自描述，客户端可二次自检）：

```json
{"interop":1,"kernel":"xray","distribution":"xray","version":"26.3.27",
 "source":"xray--core","outbounds":[{"tag":"🇺🇸 X-vless-xhttp08","protocol":"vless", …}]}
```

---

## 4. 真机验证

### 4.1 RN（X 服务端真实部署）· 只读拷贝 + 独立服务实例

命令（RN，`/tmp` 内，未碰生产服务与生产数据）：

```bash
cd /tmp/tw-rn/new && TW_WORK=/tmp/tw-rn/work TW_PORT=19481 \
  TW_CONF=/tmp/tw-rn/deploy/conf TW_SHARE=/tmp/tw-rn/deploy/out/share \
  bash tools/interop-e2e.sh
```

结果 **11 通过 / 0 失败**（真实片段：12 个可发布节点，7 个有分享元数据）：

| 步 | 结果 |
|---|---|
| 声明 | `…?interop=1&kernel=xray&distribution=xray&version=26.3.27&formats=uri,xray&url-xray=…` |
| 两条产品 | primary `content_type=text/yaml`（URI 列表）/ native `application/json`（Xray JSON） |
| **同内核 → 原生** | `本次拉取: 原生 Xray JSON —— 同内核同发行版 (xray/xray) → 取原生`，解析 7 |
| 声明缺失 → 普通话 | `本次拉取: 普通话 URI 列表 —— 地址上没有内核声明`，解析 7 |
| 原生 404 → 回退 | `…原生取件失败(http://127.0.0.1:19481/share/999…) → 回退`，解析 7 |
| 带声明 vs 裸地址 | 响应体 `sha256` 逐字节相同 |
| 两条产品逐字段 | `URI ⊆ 原生`：7/7 一致；**原生多带** `TROJAN-03:spider_x`、`vless-xhttp07:mode`、`vless-xhttp08:ech`、`SS2022-01:security=reality`（ss:// 装不下 reality，有据：`uri-representation.md §2`） |

**ECH 真值对（现验）**：RN 生产 `vless-xhttp08.json` 的 `echServerKeys`（184 字符）喂给
`xray tls ech -i`，打印的 ECH config list 是
`AGX+DQBhAAAgACA/rOgHBypsWc/LDY/WZjmK8Gm5jpe876iY7AKFphHdAgAkAAEAAQABAAIAAQADAAIAAQACAAIAAgADAAMAAQADAAIAAwADABJtb29udHYuNjg5NjY5OC54eXoAAA==`
—— `conf/lib/native.py:ech_config_list()` 算出来的值**逐字节相同**（门禁按这条向量钉住）。
即：**同内核客户端拿到的原生 JSON 里有 `echConfigList`，而 URI 那条路给不了**。

### 4.2 CC（三个客户端）· 真节点 + 真连

RN 上另起一个**持久**隔离实例（`:19482`，数据目录 `/tmp/tw-rn/pub/data`），用真实
五节点建分享（hysteria-04 / SS2022-02 / TROJAN-03 / vless-xhttp07 / vless-xhttp08），
地址：`http://107.173.154.178:19482/share/5a5b71bb…?interop=1&kernel=xray&…`

| 场景 | 客户端 | 结果 |
|---|---|---|
| **同内核 → 原生** | X 客户端（新代码） | `本次拉取: 原生 Xray JSON —— 同内核同发行版 (xray/xray)`；解析 **5** / 导入 **5** / 落盘 5 |
| 基线（对照） | X 客户端（`origin/main` 旧代码，不认声明） | 解析 **5** / 导入 **5** / 落盘 5 |
| 声明缺失 | X 客户端（新代码 + 裸地址） | `本次拉取: 普通话 URI 列表 —— 地址上没有内核声明`；5/5 |
| **对角线真连** | X 客户端三条路径 | SS2022-02 → `generate_204` = **204**（基线 204，原生 204，普通话 204） |
| **跨内核 → URI** | 未改动的 SB / M 客户端拿到的内容 | 声明地址在 CC 上 curl 出来是 **base64 的 5 行 URI**（与不带声明逐字节相同） |

**跨内核两个客户端各自的后续（不在 X 侧，如实记）**：

* **SB 客户端**（CC 上部署的是较旧构建）：`[OK] 分享配置已获取` → `[ERR] sing-box check
  失败, 旧配置未变`。部署版 `client.sh:524` 只有 `sing-box check`、**没有**"外部订阅转换器"
  那条分支；仓库版（`src/client/client.sh`）有 `to_sb.py`。把同一份 URI 列表直接喂给
  **SB 自己的转换器**：`[to_sb] 格式=share-uri 共=5 成功=5 跳过=0`，产物
  `sing-box check` 通过。→ **内容没问题，是那份部署构建没有转换器路径**（SB 侧）。
* **M 客户端**：`[ERR] 不是合法的 Mihomo 订阅 (需要顶层 proxies: 列表)`。M 客户端按设计
  只吃 mihomo YAML（自己的 `client.sh` 头部写得很明确：不用任何格式转换器）。
  → **M 客户端读不了 URI 列表**，这是跨内核互通的真实缺口（M 侧；本仓库纪律不允许我去改）。

### 4.3 一处必须让人看见的**取舍**（不是回归，但需要产品决策）

RN 的 7 节点集里有一条 `SS2022-01 = shadowsocks + REALITY`：

| 路径 | 客户端看到的 | 结果 |
|---|---|---|
| URI（普通话） | `ss://…`，**security 丢了**（ss:// 物理上装不下 reality） | 当成普通 ss 节点导入，**5 节点集里它照样进列表** |
| 原生（Xray JSON） | `security=reality` + `pbk/sid` **完整** | compat 判"这个组合不可用"→ 被 `nodefilter` 剔除（带原因） |

也就是说：全量 7 节点分享时 **原生路径落盘 6、URI 路径落盘 7** —— 差值恰好是这条
`ss+REALITY`。原生路径不是"少了一个"，而是**把 URI 路径一直藏着的真实不兼容暴露出来了**。
两条路径的行为差必须由 compat 说出来（它确实说了），但"到底该显示还是隐藏"是产品决策，
本次没有替用户决定，也没有为了让数字好看而静默降级。五节点基线集（不含该节点）两条路径
都是 5/5。

---

## 5. 门禁

```
$ bash tools/check_libs.sh
═══ 结果: 782 通过, 0 失败 ═══
```

* `origin/main`（`55c736a`，含另一条线的 ECH/载荷一致性工作）基线：**756 / 0**
* 本次新增 26 条：决策 9 条（同内核→原生 / 跨内核 / 声明缺失 / 版本不认识 / 内核不认识 /
  发行版不在清单 / 没给地址 / 地址不是 http(s) / 本机发行版探测不出来）+ 两份 `interop.py`
  sha256 相同 + 片段不算声明 + 并声明保留原有参数 + 原生产品生成器三条边界
  （ECH 真值对 / 坏输入不猜值 / 链接侧带宽→Xray Bandwidth 语法）+ 端到端 5 条
  （汇总 0 失败 + 四条路径单独可见）。
* 端到端在门禁里是**真跑**的：独立服务实例 + 真 `share.sh create` + 真 `xbd node sub`；
  找不到分享服务源码时验证台退出 3，门禁据此判**失败**（"端到端没跑就是没跑"）。
* 顺带修掉验证台自身一处风险：`grep -oE … | head -1` 会让上游吃 SIGPIPE（pipefail 下
  变 141、地址变空串）→ 改 `sed -n 1p`。

---

## 6. UNKNOWN（没证据就不猜）

| # | 事项 | 为什么没结论 |
|---|---|---|
| U1 | 第三方客户端（v2rayN / Shadowrocket / 机场面板）对**带未知查询参数**的订阅地址是否有改写行为 | 本环境没有这些客户端。**服务端侧**可证（公共服务忽略查询串、响应逐字节相同），客户端侧是否原样透传未逐一验证 |
| U2 | 同内核、**不同发行版**（fork）之间原生产物能否无损互读 | 只有"fork 能力不同"的既有结论；没有逐字段回环证据 → 规则保守走普通话 |
| U3 | `interop` 响应头通道 | 公共服务暂不支持 provider 自定义头，未实现、未验证 |
| U4 | M / SB **服务端**的声明实现 | 本次只改 X；两家服务端声明口径要在各自仓库落地后才能验"三家互读" |
| U5 | SB 客户端**仓库版**（带转换器的构建）端到端导入 X 的 URI 列表 | 只单独验了它的转换器（5/5 通过 + `sing-box check` 通过）；整条客户端流程未在 CC 上跑（部署的是旧构建） |
| U6 | M 客户端消费 URI 列表 | 现有客户端明确拒绝（要求顶层 `proxies:`）；是否有别的 M 侧入口未查 |
| U7 | 原生产品的运行期可用性（不只是解析） | 解析层等价 + 两条路径都真连 204 已验；但没有对**每个协议**都跑原生 JSON 端到端 |

---

## 7. 复现方式

```bash
# 1) 门禁（含端到端；需要 proxy-share-service 源码, 可用 TW_SERVICE= 指定）
bash tools/check_libs.sh

# 2) 端到端验证台（合成语料; 只写 /tmp, 独立端口与数据目录）
TW_XRAY_VERSION=26.3.27 bash tools/interop-e2e.sh

# 3) 拿真实部署的片段跑（只读拷贝, 仍是独立服务实例）
TW_CONF=/root/catmi/xray/conf TW_SHARE=/root/catmi/xray/out/share \
  TW_PORT=19481 bash tools/interop-e2e.sh

# 4) 单点调试
python3 conf/lib/interop.py self
python3 conf/lib/interop.py decide '<订阅地址>'
python3 conf/lib/native.py <conf> <share> <tag…>
```
