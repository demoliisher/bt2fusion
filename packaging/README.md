# 打包与开发环境

交付物是 `dist/bt2fusion.exe`，用 **Nuitka** 构建（把包编译成 C 再链接 CPython）。玩家看的文档在[仓库根目录的 README](../../README.md)，源码导读在 [`src/bt2fusion/README.md`](../src/bt2fusion/README.md)。

## 准备环境

```console
py -3.12 -m venv .venv
.venv\Scripts\pip install customtkinter nuitka pytest ruff vermin
```

**用 Python 3.12，并且不要装 Pillow。** 这两条都只影响体积，不影响功能 —— 见下。

## 构建

```console
.venv\Scripts\python packaging\build.py --clean
```

产物为 `dist/bt2fusion.exe`（8.9 MB，无控制台窗口，图标取自 `src/bt2fusion/data/favicon.ico`，双击即用）。

`--clean` 会先删掉 `dist/` 与 Nuitka 的中间目录（`launcher.build`、`launcher.dist`、`launcher.onefile-build` —— Nuitka 按入口脚本 `launcher.py` 命名，不是 `bt2fusion.*`）。这几个目录加起来有 100 MB 以上，不清会一直堆在磁盘上。

构建脚本会先检查环境，**不符合就直接拒绝构建**，而不是打个警告然后照样打出偏大的产物：

```console
$ python packaging/build.py
building with Python 3.14.7
  ERROR: Python 3.12 is required. This project is pinned to it because 3.12
         ships Tcl/Tk 8.6 while 3.13+ ship Tk 9.0, which is about twice the
         size (16.2 MB vs 8.9 MB for an identical GUI).

Refusing to build. Pass --force to override.
```

确实要用别的版本时加 `--force`。

## 版本号只写一处

版本号是 `src/bt2fusion/__init__.py` 里的 `__version__`：

- `pyproject.toml` 通过 `[tool.hatch.version]` 读它；
- `packaging/build.py` 通过 `project_version()` 读它，写进 exe 的资源信息；
- GUI 标题栏和 `bt2fusion --version` 也用它。

不要在任何地方再抄一份数字 —— 之前 exe 属性里是 `0.4.0`、标题栏里却是 `0.2.0`，就是这么来的。

## 测试与检查

```console
.venv\Scripts\python -m pytest                 # 103 个测试
.venv\Scripts\python -m ruff check .
.venv\Scripts\vermin src packaging tools tests # 验证 Python 版本下限
```

运行时的最低版本由 `vermin` 实测得出，声明为 **Python 3.10+**（打包时另受上面那条 3.12 约束）：

```console
$ .venv\Scripts\vermin src packaging tools tests
Minimum required versions: 3.10
```

提交前请确认 `pytest` 与 `ruff` 干净。**测试绝不触碰真实的游戏安装目录**，`tests/` 是隔离的；如果手工碰了真实安装，先备份、事后按哈希验证已还原。若某个改动是在修 bug，请把「还原这个修复、看测试失败」也走一遍。

> 少数 GUI 测试需要可用的 Tk，缺 Tk 的解释器下会自动 skip，所以「通过 + 跳过」的总数应当始终是 103。

## 为什么产物是 8.9 MB

体积只由**构建环境**决定，与编译标志无关。

| 构建环境 | 体积 |
|---|---|
| **Python 3.12，不装 Pillow** | **8.9 MB** |
| Python 3.14，不装 Pillow | 12.1 MB |
| Python 3.14 + Pillow | 16.2 MB |
| PyInstaller（作对比） | 30.9 MB |

界面在三种情况下**像素级完全一致**（截图的 SHA-256 相同），差别只在体积。

### 一、不要装 Pillow

这是最容易踩的坑 —— 装了它构建不会报错，只是产物白白大一截。CustomTkinter 只在 `ctk_image.py` 里 `try: from PIL import ... except ImportError: pass` 地导入它，且**只**为 `CTkImage` 服务。本项目的界面不用 `CTkImage`（窗口图标走 `iconbitmap`），所以 Pillow 根本不需要。一旦环境里有它，Nuitka 就会把 PIL 的 Python 层（`Image.py`、`TiffImagePlugin.py`、`PngImagePlugin.py`、`PdfParser.py` …）一起编译进去，并打包其扩展模块：

| | 装了 Pillow | 没装 |
|---|---|---|
| `launcher.dll`（编译后代码） | 17.7 MB | **9.6 MB** |
| PIL 扩展模块 | 10.7 MB | **0** |
| 最终 exe（Python 3.14） | 16.2 MB | **12.1 MB** |

注意 `customtkinter` 的包依赖里**本来就没有 Pillow**（只有 `darkdetect`、`packaging`）。本项目环境里出现的 Pillow 是已移除的 maliang 留下的。

### 二、用 Python 3.12 而非 3.14

3.14 带 Tcl/Tk 9.0，3.12 带 Tk 8.6，后者体积约为一半：

| | Tk 9.0（3.14） | Tk 8.6（3.12） |
|---|---|---|
| Tcl/Tk 动态库 | 6.25 MB | **3.25 MB** |

### 编译标志不影响体积

实测四个变体，产物**完全一致**（哈希不同但体积精确相同）：

| 变体 | 体积 |
|---|---|
| `--mode=onefile`（基线） | 16.23 MB |
| `+ --python-flag=no_docstrings` | 16.23 MB |
| `+ --python-flag=no_asserts` | 16.23 MB |
| `--mode=standalone` | 51.8 MB（目录，非单文件） |

所以**不要**在编译标志上找体积 —— 该动的是构建环境。

### 其他实测记录

- `--lto=yes` 在本工具链下**无法链接**（报 `undefined symbol: __QNAN` 等），不是本项目代码的问题。
- `--nofollow-import-to=PIL` 会**产出无法启动的 exe**，不要用它绕开 Pillow —— 正确做法是干脆不装。
- 复现体积对比可用 `python tools/compare_builds.py`。

> 本项目**只用 Nuitka**。早期曾保留一份 PyInstaller 配置作为备选，但它打包出的产物约 30.9 MB，且其数据收集需要额外注意，留着只会诱导人走错路，故已删除。若确实需要，`pip install pyinstaller` 后可自行编写，记得用 `collect_data_files` 收集包内数据，否则打包后读不到自带配置。

## 发布前检查

1. `pytest` 与 `ruff check .` 干净；
2. 量一下产物大小；
3. 从构建出的 exe 跑一遍 `--cli status` 和 GUI。
