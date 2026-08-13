---
title: OCR 服务
order: 20
summary: PaddleOCR-VL 1.6 双层可搜PDF / HTML / Word 三产物，含朝向还原与单卡显存策略
---

# OCR 服务

两个服务分工：**8118 持有模型**（唯一一份 VL 常驻显存），**8119 拼装产物**（一律反代 8118，不重复加载模型）。

## 1. paddle-ocr（8118）—— 模型层

- 代码：`~/cgb/ocr_server.py`（FastAPI），venv `~/cgb/.venv_paddleocr`，systemd `paddle-ocr.service`
- 引擎：**PaddleOCR-VL 1.6**（准，慢）+ 传统 **PP-OCR**（快，懒加载）
- 显存：模型常驻约 8.5G / 16G

### 接口

| 接口 | 用途 | 说明 |
|---|---|---|
| `POST /ocr` | 文件 → Markdown | 生产主接口，PMS / doc-intake / 投标审核都在用 |
| `POST /ocr_classic` | 文件 → 纯文本 | 传统 PP-OCR，快，不吃大模型 |
| `POST /ocr_ex` | **结构化输出** | 见下，做双层PDF/HTML/Word 的原料 |
| `GET /assets/<result_id>` | 版面图片打包 zip | 印章、插图，供 HTML/Word 嵌回 |
| `POST /export` | Markdown → docx/xlsx/pdf | — |
| `GET /health` | 健康检查 | — |

### `/ocr_ex` 两种模式（关键）

```bash
# ① layout：版面块 + markdown → 用来做 HTML / Word
curl -X POST 127.0.0.1:8118/ocr_ex -F "file=@x.pdf" -F mode=layout -F save_assets=1

# ② spotting：行级四边形 + 文字 → 用来做双层PDF的文字层（含朝向）
curl -X POST 127.0.0.1:8118/ocr_ex -F "file=@x.pdf" -F mode=spotting -F max_new_tokens=2048
```

`spotting` 是 PaddleOCR-VL 的隐藏能力：`predict(use_layout_detection=False, prompt_label="spotting")`，模型会**直接吐出每行文字 + 四个顶点坐标**（千分比 × 页宽高）。这是做"朝向正确的文字层"的唯一可靠来源——普通 layout 模式只有段落级矩形框，做不出竖排和斜水印。

表单参数：`mode` / `max_pixels`(默认 786432) / `max_new_tokens` / `first_page` / `last_page`(1-based 页范围) / `save_assets`。

## 2. ocr-multi（8119）—— 产物层

- 代码：`~/cgb/ocr_multi.py`（Flask），同一个 venv，systemd `ocr-multi.service`
- 自己只加载轻量 PP-OCR（约 2.5G）做快路径；VL 类一律反代 8118

### 方法一览

```bash
POST /ocr?method=<方法>   # 上传字段名 = file，支持 pdf/png/jpg
```

| 方法 | 产物 | 速度（V100，CPU 空闲） |
|---|---|---|
| `vl_all` ★ | HTML + Word + 双层可搜PDF（zip） | ~30s/页（两趟 VL） |
| `sandwich_vl` | 双层可搜PDF（VL 文字层，朝向还原） | ~20s/页 |
| `doc_vl` | HTML + Word（带版面图片/印章） | ~10s/页 |
| `sandwich_pp` | 双层可搜PDF（传统 PP-OCR 文字层） | ~1.5s/页 |
| `checkpage` | 识别核对版PDF（左原图右识别文字） | ~1.5s/页 |

**按需只跑该跑的那趟**（省一半时间）：

```bash
# 只要 HTML+Word → 只跑 layout 趟
curl -X POST "127.0.0.1:8119/ocr?method=vl_all&want=html,word" -F "file=@x.pdf" -o out.zip
# 只要双层PDF → 只跑 spotting 趟（单样直接返回文件，不套 zip）
curl -X POST "127.0.0.1:8119/ocr?method=vl_all&want=pdf" -F "file=@x.pdf" -o out.pdf
```

其他参数：`first_page` / `last_page`（页范围，输出也只含该范围）、`max_new_tokens`。

## 3. 双层PDF 的文字朝向是怎么做的

核心函数 `_put_quad()`（`ocr_multi.py`）。给定 VL 返回的四边形 `[p0,p1,p2,p3]`：

- `p0→p1` = **阅读方向**（横排向右 / 竖排向下 / 倒置向左 / 斜水印任意角）
- `p0→p3` = **行高方向**（指向该行下沿）
- 角度 `ang = (-atan2(uy, ux)) % 360`
- 离 0/90/180/270 在 12° 内 → `page.insert_text(rotate=snap)`
- 其余任意角 → `TextWriter + morph(Matrix(ang))`（斜盖的电子签章水印走这条）
- 基线起点 = 行首上沿沿行高方向下移 82%；字号 = 行高 × 0.88，再按行长收缩

**PyMuPDF 的三条约定（都是实测的，别凭印象改）**：

1. `insert_text(rotate=90)` 文字**向上**（dir = `(0,-1)`）；`rotate=270` 向下
2. `TextWriter` 的 `Matrix(ang)` 与 `insert_text` 的 `rotate` **同向**
3. 插入方法**自动跟随页面 `/Rotate`**，`page.rect` 已是视觉坐标，不需要 derotation

验收方法：把 `_put_quad(..., visible=True)` 打开，文字层会以红字可见渲染出来，直接看红字有没有贴合原文。

## 4. 单卡 V100 的两个坑（已修，别改回去）

1. **spotting 会一次性申请约 3.87GB 连续显存**（全序列 logits 转 fp32）。`max_new_tokens` 默认 4096 时必炸 → 8119 默认传 **2048**（env `VL_MAX_NEW_TOKENS`）。
2. **成败取决于空闲显存**：paddle 的 auto_growth 缓存会一路涨到 12.4G，把空间占死。修法是 `_free_gpu()`（`gc` + `paddle.device.cuda.empty_cache()`）**在推理前也清一次**，并加 **OOM 自动降档重试**（`max_new_tokens` → 1536）。修后 GPU 稳在 6.5G。

## 5. 并发策略（按实测定的，别乱调）

`ocr_server.py` 的 `gpu_slots(exclusive=)`：

- **layout / 传统OCR：可并发 2 路**（21s → 12s，1.75×，结果与串行逐字一致）
- **spotting：必须独占整卡**（并发 2 路两个请求全 OOM）

env `OCR_CONCURRENCY`（默认 2）。端点已从 `async def` 改成 `def`（FastAPI 丢线程池），所以**推理期间 `/health` 13ms 就返回**，不会再把事件循环堵死。

## 6. ccgp 抢 CPU 的问题（重要）

`ccgp@ocr` 是政采公告抓取流水线里的扫描件 OCR 环节，用 **12 个 RapidOCR CPU worker**（每个约 2 核、41 线程）。它满速跑时，VL 推理会慢 **4.7 倍**（3 页 layout：37s → 176s）。

反直觉的是：**不是抢不到 CPU**（VL 只吃 0.3 核，系统还有 31% 空闲），而是内存带宽/缓存被搅乱。所以：

- ❌ `CPUWeight` 权重无效
- ❌ **`AllowedCPUs` 限核帮倒忙**（把 paddle 圈进 8 核后更慢，110 个线程挤 8 核自旋打架）
- ✅ **只有限制 ccgp 的 CPU 总量有效**

现行方案是**动态让路**（不是永久降速）：

- 脚本 `~/cgb/ccgp_throttle.sh on|off`
- sudoers `/etc/sudoers.d/ocr-ccgp-throttle`（只放行 `systemctl set-property ccgp@ocr.service CPUQuota=*`）
- 8118/8119 用 `yield_cpu()` 上下文（引用计数），**推理期间**把 ccgp 限到 `CPUQuota=300%`，干完立刻解除
- 空闲时 ccgp 照常满速消队列
- 开关：`CCGP_THROTTLE=0` 关闭，`CCGP_THROTTLE_QUOTA` 调配额

## 7. 排障

```bash
systemctl status paddle-ocr ocr-multi
journalctl -u paddle-ocr -n 50 --no-pager
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv
curl -s 127.0.0.1:8118/health; curl -s 127.0.0.1:8119/healthz
```

| 症状 | 多半是 |
|---|---|
| 500 + `ResourceExhaustedError` | 显存不够，看 `_free_gpu` 有没有生效、是不是别处又加载了一份模型 |
| 特别慢（>60s/页） | ccgp 在抢，看 `systemctl show ccgp@ocr -p CPUQuotaPerSecUSec` 是不是没限上 |
| 改了代码不生效 | **`docker restart` 不换镜像层**；宿主 systemd 服务要 `systemctl restart` |
