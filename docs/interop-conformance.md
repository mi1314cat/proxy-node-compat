# 三家互通 · 协议一致性（跨实现，不许漂移）

三个内核**各自独立实现**了同一份「内核声明 / 格式选择」协议：

| 内核 | 实现 | 份数 |
|---|---|---|
| `xray--core` | `conf/lib/interop.py`（服务端） + `Client/lib/interop.py`（客户端） | 2 份，逐字节相同（门禁比对 sha256） |
| `mihomo--core` | `src/lib/interop.py` | 1 份，服务端与客户端共用 |
| `sing-box-core` | `src/conf/interop.py`（服务端） + `src/client/lib/interop.py`（客户端） | 2 份，逐字节相同（门禁比对 sha256） |

**独立是刻意的**：三个内核是三个独立项目，谁都不该依赖谁。代价是它们会**漂移**，
而这类漂移在运行期的表现是**静默**的：

* 服务端写 `distribution=…`、客户端读 `dist` → 客户端永远走普通话，不报错；
* 一边写 `url-<fmt>`、另一边读 `url_<fmt>` → 同上；
* 一边把"跨内核"判成 native → 客户端拿到自己读不懂的载荷，然后自己静默丢掉几条。

所以本仓库同时持有**协议语料**与**比对台**，把"不许漂移"变成可执行的检查。

---

## 1. 语料（唯一真源）

`tools/interop-vectors.json` —— 24 条声明向量 + 一组声明产出的等价性要求。

每条向量声明三件事：

* `query`：带占位符的查询串。占位符（`{{K}}` / `{{D}}` / `{{OTHER}}` / `{{U}}` …）
  由执行方替换成**自己词表里的真实值**，所以同一份语料对三个内核都成立。
* `want`：**只写家族**（`native` / `uri:<为什么>`），不写实现文案 ——
  文案允许多几个字，判据是"该不该拿原生"。
* `forms`：这条向量跑哪种入参形态（默认见下）。

### 入参形态（四种，必须都成立）

| 形态 | 含义 | 谁在用 |
|---|---|---|
| `full-url` | `http://host:9443/share/<token>?<声明>` | **生产主路径**：客户端直接吃服务端给的订阅地址 |
| `bare` | 只有查询串，例如 `interop=1&kernel=…` | `interop.py decide` 的 CLI、手工调试；**协议承诺支持的形态** |
| `bare-q` | `?` + 裸查询串 | 有的调用方会把 `?` 一起带进来 |
| `raw` | 整串原样（用于"空"与"一条没有查询串的地址"两条边界） | 边界 |

**同一条向量在 `bare` / `bare-q` / `full-url` 下决策不同，本身就是缺陷。**

个别向量的语义只属于某一种形态（例如"片段里的同名字段不算声明" —— `#片段` 这个概念
只有完整地址才有，裸查询串里 `#` 属于最后一个参数的值，那是查询串的语法而不是实现缺陷）。
这类向量可以在语料里用 `"forms": [...]` 收窄，但**必须同时写 `_note` 说明理由**，
并且 `tests/test_interop_corpus.py` 会强制这一点 —— 否则"收窄"就成了悄悄少判一条的借口。

---

## 2. 比对台

```bash
python3 tools/interop-conformance.py \
    --impl x-server:xray--core/conf/lib/interop.py \
    --impl x-client:xray--core/Client/lib/interop.py \
    --impl m:mihomo--core/src/lib/interop.py \
    --impl sb-server:sing-box-core/src/conf/interop.py \
    --impl sb-client:sing-box-core/src/client/lib/interop.py
```

（路径按你本地检出位置改。同一份实现出现多次会各自单独验。）

它跑四件事，**全看行为、不看源码**：

1. **① 决策一致性**：每条向量 × 每种形态，五份实现的 `(choice, reason)` 必须相同，
   且必须落在语料的 `want` 家族里 —— 后者防的是"五个一起错得一样"。
2. **①b 形态敏感性**：同一向量在 `bare` 与 `full-url` 下决策必须相同。
3. **② 声明产出一致性**：`build_declaration()` + `declaration_query()` 归一化后
   参数名集合必须相同。（值的转义方式允许不同：M 保留 `://` 可读性，X/SB 全编码，
   两者 parse 之后等价。）
4. **③ 交叉可读性**：同内核的 A 产出的声明，B 必须能读成 `native` 且取到同一个地址。

退出码 0 = 零分歧。

---

## 3. 已经抓到过的真实缺陷（留档，别再犯）

### 3.1 `://` 当"是不是裸查询串"的判据（三家都有，M 先暴露）

`parse_declaration()` 原来这样分形态：

```python
if "?" in s and "://" in s or s.startswith("?"):
    q = urllib.parse.urlsplit(s).query if "://" in s else s.lstrip("?")
elif "=" in s and "://" not in s:
    q = s                      # ← 判"裸查询串"用的是"串里没有 ://"
else:
    q = ""
```

* **M 先暴露**：M 的 `URL_SAFE = "/:@[]"` 让 `url-*` 的值**保留 `://` 原样**
  （可读性更好），于是 **M 自己产出的裸查询串里也有 `://`** → 掉进 `else` →
  `parse_declaration` 返回 `None` → `decide` 给 `no-declaration` →
  **静默走普通话**。也就是说 M 的 `interop.py declare` 的输出喂回
  `interop.py decide`，永远拿不到原生。
* **X / SB**：它们把 `url-*` 值**全编码**，所以不会踩到自己；但同一个入参
  （第三方给的、url 值未编码的裸查询串）一样被判成"没有查询串" ——
  **协议承诺了支持 `bare` 形态，就得三种输入都成立**。

#### 修法（★ 这里有个坑，第一版修法就是错的）

判据必须换成**真探测 scheme**，**不能**只是"换一个子串判据"：

```python
s = str(text or "").strip()
if not s:
    return None
if s.startswith("?"):
    q = s.lstrip("?")
elif urllib.parse.urlsplit(s).scheme:          # ★ 真探测
    q = urllib.parse.urlsplit(s).query
elif "=" in s:
    q = s                                       # 裸查询串
else:
    q = ""
```

**错的那一版**（本文档最早写的、也是当时发给实施方的）：

```python
if s.startswith("?"):      q = s.lstrip("?")
elif "://" in s:           q = urllib.parse.urlsplit(s).query   # ← 错在这
elif "=" in s:             q = s
else:                      q = ""
```

它错在：**裸查询串里本身就有 `://`**（`url-xray=http://…`），第二个分支照样命中
→ `urlsplit(裸查询串).query` = 空串 → 依然静默 `no-declaration`。
也就是说"把 `"://" not in s` 改成 `"://" in s`"并没有改变判据的**性质** ——
它还是在看子串，而不是在看"这串有没有 scheme"。

修完必须验**三种形态**都成立、且 `decide()` 三项结果逐字段相同：

1. 裸查询串（`interop=1&…&url-xray=http://…`）
2. `?` + 裸查询串
3. 完整订阅地址（`http://host:9443/share/<token>?interop=1&…`）

**这个坑本身值得留档**：它说明"照着别人的修法写"和"照着别人的**理由**写"是两回事 ——
第一版的理由是"看有没有 scheme"，写法却是"看有没有子串"，两者不等价。

### 3.2 教训

* 这类缺陷**不会报错**，只会让原生格式永远拿不到 —— 与"声明字段名写错"同一类。
* 因此每个内核侧也要有**自己的**断言（不能只靠这个台子：台子要三份检出才跑得起来，
  而内核的 CI 只有自己那一份）。内核侧最小断言：
  `parse_declaration(declaration_query(build_declaration(...)))` 的 `recognized`
  为真，且 `bare` 与 `full-url` 两种形态的 `decide()` 三项结果完全相同。
* 反向验证：把修好的判据临时还原，这条断言必须红。
