# 源码导读

给想改代码的人。普通玩家看[仓库根目录的 README](../../README.md) 就够了 —— 那是给玩家看的，这里讲的是实现细节。

## 目录

```
src/bt2fusion/
├── __init__.py       # 公开 API、__version__
├── channels.py       # 渠道注册表（key / channel_id / 中文名）
├── config.py         # 用户设置（记住的安装目录）
├── errors.py         # 异常层级
├── fsutil.py         # 磁盘枚举与文件查找
├── game.py           # 定位 / 识别 / 切换 / 启动 —— 核心逻辑
├── profiles.py       # 读取打包的渠道配置数据
├── shortcuts.py      # 从 .lnk 里找安装目录
├── gui.py            # CustomTkinter 窗口（这就是产品）
├── cli.py            # 命令行（顺手提供的便利）
└── data/
    ├── favicon.ico   # 窗口图标 / exe 图标
    └── profiles/<渠道>/platform.xml, platform_exm.ini
```

渠道配置以**数据文件**形式随源码存放，不内嵌为 Python 字面量 —— 这样替换、比对、追责都简单。

## 从源码运行

本项目**不是 `pip install` 用的包**，交付物是 exe，仓库只是源码。所以不需要安装本包，装好依赖即可（测试与打包都直接从 `src/` 读源码）：

```console
py -3.12 -m venv .venv
.venv\Scripts\pip install customtkinter nuitka pytest ruff vermin

.venv\Scripts\python -m bt2fusion.gui      # 跑图形界面
```

环境版本、体积、打包相关的约定见 [`packaging/README.md`](../../packaging/README.md)。

## 命令行

```console
.venv\Scripts\python -m bt2fusion status   # 查看当前渠道
.venv\Scripts\python -m bt2fusion list     # 列出全部渠道
.venv\Scripts\python -m bt2fusion set 4399 # 切换到你自己的渠道
.venv\Scripts\python -m bt2fusion repair   # 配置文件缺失时重建
.venv\Scripts\python -m bt2fusion launch   # 启动游戏
.venv\Scripts\python -m bt2fusion find     # 列出找到的全部安装目录
.venv\Scripts\python -m bt2fusion where    # 打印当前使用的安装目录
```

`pyproject.toml` 里也注册了 `bt2fusion` 这个命令，但它只在你确实 `pip install -e .` 之后才存在 —— 本项目不要求这么做，用 `python -m` 即可。

自动识别失败时，可对任意命令加 `-C/--path` 显式指定安装目录：

```console
.venv\Scripts\python -m bt2fusion status --path "D:\Wooduan\SSJJ2-WD"
```

也可以用 `set-path` 记住目录（存在 `%APPDATA%\bt2fusion\config.json`）：

```console
.venv\Scripts\python -m bt2fusion set-path "D:\Wooduan\SSJJ2-WD"
```

## 当库用

源码是 src 布局，直接把 `src` 加进 `PYTHONPATH` 即可，无需安装：

```python
from bt2fusion import CHANNELS, detect, find_all, rewrite

result = detect()
print(result.channel)            # <Channel 4399>
print(result.consistent)         # 配置与注册表是否一致

rewrite('4399')                  # 切换到自己的渠道
print(find_all())                # 机器上找到的全部安装
```

## 当前渠道是怎么判定的

`detect()` 按下面的优先级判断，全部为**只读**操作：

1. **配置文件的实际内容** —— 权威来源。这才是游戏启动时真正读取的，也是切换时会改写的。
2. 日志 `myeasylog.log` 里的 `platform_config_.channel_id_:N`
3. 注册表（**仅供参考，不作为判断依据**）

### 为什么注册表不作数

启动器确实会把渠道写进注册表（`HKLM\SOFTWARE\WOW6432Node\Wooduan\SSJJ2\COMMON`），但它只用于 `platform.xml` 损坏时自动恢复，而且是**机器级**状态：

- 在共用或重装过系统的机器上，它可能是**上一次安装 / 上一个用户**残留的值；
- 网吧环境不该依赖注册表 —— 一台机器装了那么多游戏，逐个读注册表不现实，也不该要求用户去查注册表。

所以注册表只在配置文件与日志都无法判定时兜底，并且**仅用于显示**：

```console
$ bt2fusion status
install dir : D:\Wooduan\SSJJ2-WD
channel     : 4399 (id=6)  [from config files]
registry    : 4399 (platform='p4399', channel_id=6)
```

两者不一致时会明确提示，但**以配置文件为准**：

```
note        : config and registry disagree; the registry updates when the game
              is next launched
```

## 安装目录是怎么找到的

依次尝试：

1. **快捷方式** —— 桌面与开始菜单里指向 `WDlauncher.exe` 的 `.lnk`（最快）
2. **网吧布局** `<盘符>:\网络游戏\生死狙击2`（以及 `网络游戏\SSJJ2`），遍历所有盘
3. 官方安装器布局 `<盘符>:\Wooduan\SSJJ2-WD`
4. 上次记住的目录（`%APPDATA%\bt2fusion\config.json`）
5. 全盘扫描 `WDlauncher.exe`（最慢，仅在前述都失败时）

盘符按**已用空间从大到小**排序 —— 游戏通常装在数据最多的那个盘。「记住上次的目录」的优先级低于网吧路径：网吧每次可能是不同机器，本地状态本来就没有意义，自动识别必须可靠。

### 快捷方式按「目标」匹配，不按名字

游戏在国服叫 `生死狙击2`，国际名是 `Battle Teams 2`，玩家的桌面快捷方式**可能用任意一个名字**，所以按文件名去猜（`生死` / `狙击` / `SSJJ`）会漏掉。

本项目改为解析 `.lnk` 里记录的目标路径，**与快捷方式叫什么名字无关**，只要能解析出 `WDlauncher.exe` 所在目录即可。解析不依赖任何第三方库，且每个候选路径都会**经过文件系统验证**才被采信，因此二进制噪声不会造成误判。

实测：本机 ~130 个快捷方式里解析出 1 个候选，无假阳性；定位耗时从全盘扫描的约 1500 ms 降到约 16 ms。

> 顺网/云更新的 `网络游戏` 目录若不止一款游戏，本项目只会查找生死狙击2 对应的子目录，不会误改其他游戏。

### 同一台机器上的多份安装

装了多份时 `find_all()` 会列出全部：

```python
>>> from bt2fusion import find_all
>>> find_all()
['D:\\网络游戏\\生死狙击2', 'C:\\Wooduan\\SSJJ2-WD']
```

## 两个配置文件

| 文件 | 大小 | 作用 |
|---|---|---|
| `platform.xml` | 4320–6032 B | 渠道主体配置 |
| `platform_exm.ini` | 32–56 B | 附加参数（`sub_channel_id`） |

- `platform_exm.ini` 的含义是确定的 —— 网吧渠道（顺网/官服/易乐玩）那份是明文：

  ```ini
  [channel]
  sub_channel_id=8192
  ```

- `platform.xml` 的内容是**加密的**：8 字节分组、ECB 模式（长度不全是 16 的倍数，可排除 AES-ECB）。但**本项目不需要解密**，因为它是整份替换、从不解析内容 —— 识别渠道时也只是把文件字节与内置数据逐一比对（见 `game.detect_from_config`）。这也是渠道配置必须**原样携带数据文件**、不能「现场生成一份」的原因。
- 识别时 `platform.xml` 优先于 `platform_exm.ini`；渠道 id 与文件名对照表在 `channels.py`。
- `netbar` 就是**网吧渠道**（`channel_id=2`）：网吧的无盘系统默认装的就是它。它是一个**三合一入口 —— 顺网 / 官服 / 易乐玩**，这三者在游戏启动器里就能直接切换；官服的独立配置（`official`）同时存在，两者不冲突。所以网吧玩家的操作是**从它切走**（自己的号在 bilibili、4399 等渠道时）。

## 改代码时的几条硬约束

- **不要凭空发明用户可见的行为。** 受众是不懂技术的玩家，界面上任何「为什么需要它」的说法都必须是真的。
- **测试绝不写真实游戏安装目录。** `tests/` 完全隔离；手动碰真实安装前先备份，事后按哈希验证已还原。
- **内置渠道配置是第三方数据。** 署名必须同时出现在玩家 README、`data/profiles/README.md` 和 **GUI 内部**（用户可能只拿到 exe）。有测试兜底。
- **改 GUI 前先看渲染结果**，不少布局 bug 在代码里看不出来：`python tools/capture_window.py "渠道切换" out.png`
- **改打包前先量产物。** 跑一遍 `packaging/build.py`，再从构建出的 exe 启动 `--cli status` 与 GUI，并对比体积（见 [`packaging/README.md`](../../packaging/README.md)）。
- **修 bug 时证明测试有效**：把修复还原，确认测试失败，再恢复。
