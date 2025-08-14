# gallery-dl

## 功能

本插件基于强大的 `gallery-dl` 工具，可以从众多网站下载图片或视频库。

## 使用方法

您可以通过以下命令使用本插件：

- `gdl <链接>`: 下载指定的图片或视频库。
- `gdl _pixiv <关键字>`: 下载 pixiv 热门插画。
- `gdl _proxy <url>`: 设置下载时使用的 HTTP/SOCKS 代理。
- `gdl _proxy`: 删除已设置的代理。
- `gdl update`: 检查并更新 `gallery-dl` 到最新版本。

## 支持的网站

`gallery-dl` 支持的网站列表非常广泛：

- [支持的网站列表](https://github.com/mikf/gallery-dl/blob/master/docs/supportedsites.md)

## 可选依赖

如果使用下载视频功能，需要 `ffmpeg`。  
为了支持某些特定网站或功能，可能需要安装额外的依赖库：

- [可选依赖说明](https://github.com/mikf/gallery-dl?tab=readme-ov-file#optional)

## 配置文件

### 配置文件路径

本插件的配置文件位于 PagerMaid 工作目录下的 `data/gdl/config.json`。

### 示例：使用 Cookie、用户名密码或 oauth 登录

部分网站需要登陆才能访问资源，可以在 `config.json` 中按以下配置。

```json
{
    "extractor": {
        "twitter": {
            "cookies": "data/gdl/cookies-x-com.txt"
        },
        "iwara": {
            "username": "example",
            "password": "example"
        }
    },
    "cache": {
        "file": "data/gdl/.cache/gallery-dl/cache.sqlite3"
    }
}
```

对于需要 OAuth 认证的网站（如 Pixiv），按以下步骤操作：

1.  进入 PagerMaid 工作目录下的 `data/gdl` 目录。如果使用容器，需在容器内执行此操作。
2.  执行以下命令（以 Pixiv 为例）并根据屏幕提示完成认证流程：
    ```bash
    export HOME=$PWD
    gallery-dl oauth:pixiv
    ```

### 官方文档

参考 `gallery-dl` 的官方文档来获取更详细的配置信息：

- [配置文档](https://gdl-org.github.io/docs/configuration.html)
- [配置示例](https://github.com/mikf/gallery-dl/blob/master/docs/gallery-dl-example.conf)
- [详细配置示例](https://github.com/mikf/gallery-dl/blob/master/docs/gallery-dl.conf)

## 注意事项

> **请注意**：通过非官方 API 方式抓取资源可能导致网站账户被封禁。同时，在配置文件中存储的 Cookie 或密码存在泄露风险。请自行承担使用本插件所带来的全部风险。
