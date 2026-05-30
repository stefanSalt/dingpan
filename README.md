# 盯盘悬浮窗

一个常驻桌面的国际现货 / 期货行情**悬浮窗**：无边框、可置顶、半透明、可整窗拖动，
默认盯**现货黄金、现货白银、WTI 原油、布伦特原油**，每隔数秒自动刷新。

- 技术栈：Python + PySide6（取数仅用标准库 `urllib`，运行依赖只有 PySide6）
- 数据源：新浪财经免费行情接口（无需 API key）
- 三种显示模式：**简略 / 标准 / 详细**，可右键切换
- 可在「品种管理」里**添加 / 移除 / 排序**品种，添加时通过接口实时校验并显示官方名称
- 开发在 WSL，发布为 **Windows 原生 exe**（通过 GitHub Actions 打包）

---

## 三种显示模式

| 模式 | 每行内容 | 适用 |
|------|----------|------|
| 简略 | `简称  现价  ▲涨跌幅%` | 最省地方 |
| 标准（默认） | `名称  现价  涨跌额  涨跌幅%` | 日常 |
| 详细 | 标准 + `最高 / 最低 / 昨收 / 更新时间` | 看细节 |

> 颜色默认**红涨绿跌**（A 股习惯），可在「设置」中切换为国际惯例（绿涨红跌）。

---

## 操作

- **拖动**：在窗口任意位置按住左键拖动；位置自动记忆。
- **右键菜单**：显示模式、添加品种、设置、置顶开关、退出。
- **系统托盘**（若环境支持）：双击图标显示/隐藏；右键同样有菜单。

---

## 本地开发运行（WSL / Linux）

```bash
# 方式一：脚本一键（首次会自动建 venv 装依赖）
./run.sh

# 方式二：手动
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m dingpan.main
```

仅验证数据层（无需 GUI）：

```bash
.venv/bin/python -m dingpan.sina_client XAU CL OIL
```

运行测试：

```bash
.venv/bin/python tests/test_sina_client.py     # 直接运行
# 或： .venv/bin/python -m pytest -q
```

> WSL 下通过 WSLg 显示 GUI，仅用于开发自检；正式使用请用下面打包出的 Windows exe。

---

## 打包为 Windows exe（GitHub Actions）

仓库已带工作流 `.github/workflows/build-windows.yml`：

- **push 到 `main`**：在 `windows-latest` 上用 PyInstaller 打包，产物以 **artifact**（`dingpan-windows-exe`）上传，可在该次 Actions 运行页面直接下载。
- **push `v*` 标签**（如 `v0.1.0`）：额外创建 **GitHub Release** 并附上 exe。

```bash
git tag v0.1.0
git push origin v0.1.0
```

最终用户下载 `盯盘.exe`，**双击即可运行**，无需安装 Python。

本地也可打包（在 Windows 上）：

```bat
pip install -r requirements-build.txt
pyinstaller --noconfirm dingpan.spec
:: 产物在 dist\盯盘.exe
```

> 想自定义图标：把一个 `assets/icon.ico` 放进仓库即可，运行时与打包都会自动使用。

---

## 配置文件 `config.json`

首次运行自动在程序目录生成（exe 模式下在 exe 同目录）。字段：

| 字段 | 含义 | 取值 |
|------|------|------|
| `symbols` | 盯盘品种代码（不带 `hf_`） | 如 `["XAU","XAG","CL","OIL"]` |
| `display_mode` | 显示模式 | `compact` / `standard` / `detailed` |
| `refresh_interval` | 刷新间隔（秒） | 1 ~ 60 |
| `opacity` | 不透明度 | 0.3 ~ 1.0 |
| `font_size` | 字号（pt） | 8 ~ 40 |
| `color_scheme` | 配色 | `cn`（红涨绿跌）/ `intl`（绿涨红跌） |
| `always_on_top` | 是否置顶 | `true` / `false` |
| `win_x` / `win_y` | 窗口位置 | `-1` 表示用默认位置 |

---

## 数据源说明与免责声明

- 行情来自新浪财经公开接口 `https://hq.sinajs.cn/`，请求需带 `Referer` 头、响应为 GBK 编码（程序已处理）。
- 该接口为**非官方**，新浪可能随时变更或限制；遇到取不到数据时窗口会**保留上一次的值**并在右上角显示橙色状态点。
- 国际品种用前缀 `hf_`（如黄金 `hf_XAU`、WTI 原油 `hf_CL`）。「品种管理」里内置了常用品种目录，也可手输代码，添加时会实时校验。
- **数据仅供参考，存在延迟，不构成任何投资建议；据此交易风险自负。**
