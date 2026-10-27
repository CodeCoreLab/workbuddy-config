# 安全政策

## 这个仓库的特殊之处

`workbuddy-config` 是**配置模板仓**，不是代码仓。

仓库里的 `USER.md` / `MEMORY.md` 提供了 `{{占位符}}` 供填写**真实信息** ——
而这些信息包括：

| 类别 | 例子 | 泄露后果 |
|---|---|---|
| **凭据位置** | env 文件路径、密钥路径、私有仓库账号 | 攻击者可直接读取凭据 |
| **内网拓扑** | 服务器 IP、端口、跳板机配置、数据库地址 | 可画出内网结构，为进一步攻击铺路 |
| **内部系统名** | Zabbix / InfluxDB / 内部 Git 平台 | 针对性攻击的入口清单 |
| **个人信息** | 团队成员姓名、岗位、城市 | 钓鱼与社工攻击素材 |

**因此：本仓的公开内容应始终保持为「未填写的模板」。**

## 报告安全问题

如果你在模板里发现了**真实凭据被硬编码进仓库**（应该是 `{{占位符}}` 却写成了真值），
或者发现了会让人误提交敏感信息的缺陷，请用 GitHub 私密漏洞报告：

[Security → Report a vulnerability](https://github.com/CodeCoreLab/workbuddy-config/security/advisories/new)

| 阶段 | 目标时间 |
|---|---|
| 确认收到 | 48 小时 |
| 初步评估 | 7 天 |
| 发布修复 | 视严重程度，14 天内 |

## 使用者须知

### 一定要做的事

1. **在本仓之外填写真实值**
   ```bash
   git clone https://github.com/CodeCoreLab/workbuddy-config.git
   cp -r workbuddy-config ~/.workbuddy/
   cd ~/.workbuddy/          # ← 在这里填真实值，不是在克隆目录里
   ```
2. **提交前自查**
   ```bash
   git diff --cached          # 逐行看要提交的内容
   grep -n '{{' *.md         # 查还有哪些占位符没替换（提醒你别提交）
   ```
3. **先建私有仓库**
   团队使用的话，第一步就是 `git init` 到一个**私有**仓库，而不是 fork 本仓。

### 千万别做的事

- ❌ 在本仓填入真实 IP、密钥路径、服务器地址
- ❌ 把填好的 `USER.md` / `MEMORY.md` 提交到任何**公开**仓库
- ❌ 在 Issue / PR 里贴出填好真实值的配置全文
- ❌ 把凭据**值**（不是变量名）写进 `MEMORY.md` ——
  P0 规则第一条就是「所有密码/API Key/Token 从环境变量读取」，
  配置文件里只应出现**变量名**

### 已经提交了怎么办

**先轮换凭据，再处理历史。** 顺序不能反 ——
历史改写需要时间，期间凭据一直是暴露状态。

```bash
# 1. 立刻轮换所有相关凭据（密钥、token、密码）
#    —— 这一步最重要，改历史不能代替轮换

# 2. 从索引移除（保留本地文件）
git rm --cached USER.md MEMORY.md

# 3. 改写历史（会重写所有 commit 的 SHA）
pip install git-filter-repo
git filter-repo --path USER.md --path MEMORY.md --invert-paths

# 4. 强制推送
git push --force
```

> ⚠️ `git filter-repo` 会重写所有提交。如果仓库已被 fork 或被他人 clone，
> 历史无法真正收回 —— **这也是为什么第 1 步的轮换不能省**。
> 详细说明见 [GitHub 官方文档](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。

## 仓库自身的防护

| 措施 | 说明 |
|---|---|
| `.gitignore` | 已预置 `USER.local.md` / `MEMORY.local.md` / `.env` / `*.pem` / `*.key` / `id_rsa*` 等忽略规则 |
| CI 检查 | 每次 push 扫描是否出现疑似真实凭据 / 内网 IP |
| 占位符一致性 | CI 校验模板文件中的 `{{...}}` 语法正确、无残留真实值 |
| 链接检查 | CI 校验 README 里的内部链接不断链 |

## 已知边界

| 边界 | 说明 |
|---|---|
| **无法阻止你填真实值** | `.gitignore` 只挡特定文件名，不理解「这个 IP 是敏感信息」 |
| **CI 扫描是启发式的** | 能发现明显的私钥、内网 IP 段，但不能保证零漏报 |
| **已泄露的历史无法撤回** | git 历史一旦推送出去，除非轮换凭据，否则等于公开 |
