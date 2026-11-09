# 服务器信息

## 连接方式

| 项目 | 值 |
|------|------|
| 地址 | 10.3.10.88 |
| 用户 | root |
| 密码 | hyoa@123 |
| SSH | `ssh root@10.3.10.88` |

## 服务器配置

| 项目 | 值 |
|------|------|
| 主机名 | ecology |
| 操作系统 | CentOS Linux 7 (Core) |
| CPU | 8 核 |
| 内存 | 31G（已用 17G，可用 12G） |
| 磁盘 | 800G（已用 679G，可用 122G，85%） |
| Swap | 15G |

## Redis

| 项目 | 值 |
|------|------|
| 版本 | 6.2.14 (源码编译) |
| 安装路径 | `/usr/redis/` |
| 二进制 | `/usr/redis/bin/redis-server` |
| 配置文件 | `/usr/redis/conf/redis.conf` |
| 数据目录 | `/usr/redis/data/` |
| 日志 | `/usr/redis/log/redis.log` |
| 端口 | 6379 |
| 密码 | 无 |
| systemd | `redis.service` (已启用开机自启) |

常用命令：
```bash
systemctl status redis      # 查看状态
systemctl restart redis     # 重启
/usr/redis/bin/redis-cli     # 连接
```

## 已安装软件

| 软件 | 状态 | 版本 |
|------|------|------|
| Redis | ✅ | 6.2.14 |
| Python 2 | ✅ | /usr/bin/python2 |
| Python 3 | ❌ 未安装 | — |
| Git | ✅ | 1.8.3.1 |
| Yum | ✅ | 3.4.3 |
| Java | ❌ 未安装 | — |
| Docker | ❌ 未安装 | — |

## 运行中的服务

- SSH (端口 22)
- Redis (端口 6379, systemd 管理)

## 部署说明

该服务器目前安装了 Redis，作为 Python 后端部署目标还需要：
1. 安装 Python 3（`yum install python3` 或编译安装）
2. 安装项目依赖
3. 配置 Nginx 反向代理
4. 配置 systemd 服务
5. Oracle 数据库在另一台机器 (10.3.10.87:1521)

> 内网服务器。Oracle DB 在 10.3.10.87，本机 (10.3.10.88) 为应用部署目标。

## E9 SSO 单点登录

### 接口信息

| 项目 | 本地 | 线上 |
|------|------|------|
| E9 路径 | `D:\software\weaver\ecology` | `/usr/weaver/ecology` |
| HTTP 端口 | 8098 | 8443 (HTTPS) |
| SSO 端点 | `POST /ssologin/getToken` | 同左 |
| 验证端点 | `GET /systeminfo/version.jsp?ssoToken=xxx` | 同左 |

### 认证流程

```
第三方系统 → POST /ssologin/getToken (appid + loginid) → 返回 token
第三方系统 → 带 ssoToken 访问 E9 任意页面 → 已登录状态
```

> 标准 SSO 方案：只需 appid + loginid（不需要密码），通过 IP 白名单认证。
> appid 配置在 `WEB-INF/prop/weaverloginclient.properties`，映射 appid → IP 地址。

### 本地配置（已完成）

| 文件 | 修改 |
|------|------|
| `WEB-INF/web.xml` | 添加 getToken Servlet + WeaverLoginFilter |
| `WEB-INF/weaver_security_config.xml` | `is-login-check` 改为 `false` |
| `WEB-INF/prop/weaverloginclient.properties` | `ssss=127.0.0.1` (appid=ssss, IP=本机) |

### 定制 SSO（SimpleSSOAction）

服务器上还有定制 SSO 接口（密码验证）：
- 端点: `POST /rest/integration/simplesso/getToken` (通过 RestDispatcherServlet)
- 参数: `loginid` + `password`（验证 hrmresource 表密码）
- 存储: `sso_login_oa_lzgaj` 表
- 销毁: `POST /rest/integration/simplesso/destroyToken`

### 官方文档

- PDF: [第三方单点登录 Ecology 方案](https://e-cloudstore.com/e9/file/Third-partysinglesign-onEcologysolution.pdf)
