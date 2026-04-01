# log2pr 测试指南

本文档介绍如何测试 log2pr 的自动修复功能。

## 测试前准备

### 1. 配置 GitHub App

1. 在 GitHub 上创建一个 GitHub App：
   - 访问 https://github.com/settings/apps
   - 点击 "New GitHub App"
   - 配置以下权限：
     - **Contents**: Read and write
     - **Issues**: Read and write
     - **Pull requests**: Read and write
   - 设置 Webhook URL（使用 ngrok 或 smee.io）
   - 生成 Private Key 并下载

2. 安装 GitHub App 到你的测试仓库

### 2. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件，填入你的配置
GITHUB_APP_ID=你的App ID
GITHUB_APP_PRIVATE_KEY_PATH=keys/private_key.pem
GITHUB_WEBHOOK_SECRET=你的Webhook密钥
ANTHROPIC_AUTH_TOKEN=你的API Token
ANTHROPIC_BASE_URL=https://qianfan.baidubce.com/anthropic/coding
```

### 3. 放置私钥

```bash
# 将下载的 private key 放到 keys 目录
cp ~/Downloads/private-key.pem keys/private_key.pem
```

### 4. 启动服务

```bash
# 本地开发
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 或使用 Docker
docker build -t log2pr .
docker run -p 8000:8000 --env-file .env -v ./keys:/app/keys log2pr
```

### 5. 暴露 Webhook 端点

使用 ngrok 或 smee.io 将本地服务暴露到公网：

```bash
# 使用 ngrok
ngrok http 8000

# 或使用 smee.io
smee -u https://smee.io/你的频道ID -t http://localhost:8000/webhook
```

将生成的 URL 配置到 GitHub App 的 Webhook URL（格式：`https://xxx/webhook`）。

## 测试步骤

### 测试 1: KeyError 自动修复

1. **创建 Issue**

   在你的测试仓库创建一个 Issue，标题和内容如下：

   ```
   标题: KeyError in user_service.py

   内容:
   报错日志如下：

   Traceback (most recent call last):
     File "examples/buggy_code.py", line 75, in <module>
       name = get_user_name(user)
     File "examples/buggy_code.py", line 14, in get_user_name
       return user_dict["name"]
   KeyError: 'name'

   测试步骤：调用 get_user_name 函数时，字典中没有 'name' key。
   ```

2. **触发自动修复**

   在 Issue 评论区回复：
   ```
   @auto-fix
   ```

3. **观察结果**

   - log2pr 会在评论区回复进度
   - 几秒后会创建一个 PR
   - PR 中会包含修复后的代码

### 测试 2: TypeError 自动修复

```
标题: TypeError in calculate_discount function

内容:
报错日志如下：

Traceback (most recent call last):
  File "examples/buggy_code.py", line 82, in <module>
    result = calculate_discount(price, discount)
  File "examples/buggy_code.py", line 26, in calculate_discount
    discounted = price * discount_rate
TypeError: unsupported operand type(s) for *: 'float' and 'NoneType'

当 discount_rate 为 None 时触发此错误。
```

### 测试 3: IndexError 自动修复

```
标题: IndexError in process_items function

内容:
报错日志如下：

Traceback (most recent call last):
  File "examples/buggy_code.py", line 89, in <module>
    result = process_items(items)
  File "examples/buggy_code.py", line 41, in process_items
    result.append(items[2])
IndexError: list index out of range

当列表元素少于 3 个时触发此错误。
```

### 测试 4: ZeroDivisionError 自动修复

```
标题: ZeroDivisionError in divide_numbers function

内容:
报错日志如下：

Traceback (most recent call last):
  File "examples/buggy_code.py", line 96, in <module>
    result = divide_numbers(10, 0)
  File "examples/buggy_code.py", line 53, in divide_numbers
    return a / b
ZeroDivisionError: division by zero

当除数为 0 时触发此错误。
```

## 预期行为

### 成功流程

1. 用户在 Issue 评论 `@auto-fix`
2. log2pr 回复：
   ```
   🔍 正在分析 Traceback...
   我正在仔细阅读错误日志，定位问题根源。
   ```
3. log2pr 搜索相关代码并读取文件
4. log2pr 回复分析结果
5. log2pr 创建 PR 并回复：
   ```
   🎉 修复完成！
   Pull Request 已创建: #xxx
   请审查并合并。感谢使用 log2pr！
   ```

### 失败流程

如果自动修复失败，log2pr 会回复：
```
❌ 自动修复失败

**错误类型**: xxx
**错误详情**:
```
xxx
```

请检查 Issue 内容或联系管理员。
```

## 调试技巧

### 查看日志

```bash
# 本地运行时，日志会输出到控制台
# 日志格式示例：
# 2026-03-31 12:34:56.789 INFO     app.main - 🚀 log2pr application initialized
# 2026-03-31 12:35:00.123 INFO     app.routers.webhook - [Webhook] Received event: issue_comment, delivery: xxx
# 2026-03-31 12:35:00.456 INFO     app.routers.webhook - [AutoFix] Starting workflow for owner/repo issue #1
```

### 常见问题

1. **签名验证失败**
   - 检查 `GITHUB_WEBHOOK_SECRET` 是否正确
   - 确保在 GitHub App 设置中使用相同的 secret

2. **鉴权失败**
   - 检查私钥文件路径是否正确
   - 确保私钥文件可读

3. **AI 调用失败**
   - 检查 `ANTHROPIC_AUTH_TOKEN` 和 `ANTHROPIC_BASE_URL`
   - 确保网络可以访问 API 端点

4. **PR 创建失败**
   - 确保 GitHub App 有正确的仓库权限
   - 检查分支名是否已存在

## Docker 部署

```bash
# 构建镜像
docker build -t log2pr:latest .

# 运行容器
docker run -d \
  --name log2pr \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/keys:/app/keys:ro \
  log2pr:latest

# 查看日志
docker logs -f log2pr

# 健康检查
curl http://localhost:8000/health
```

## 生产环境建议

1. 使用 HTTPS
2. 配置日志收集（如 ELK、CloudWatch）
3. 设置监控和告警
4. 使用 secrets 管理敏感信息
5. 配置速率限制
