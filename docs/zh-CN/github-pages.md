# GitHub Pages

[English](../en/github-pages.md) | [简体中文](github-pages.md)

GitHub Pages 托管只读工作台：已保存对话、方法、代码、测试、结果和媒体。它不运行 Python、Docker 工作容器或实时智能体，不需要模型密钥。创建、构建和运行新项目仍使用本地应用。

## 托管方式与地址

在线工作台：**[xxiao053.github.io/strategy-agent-lab](https://xxiao053.github.io/strategy-agent-lab/)**；项目源码：**[GitHub 仓库](https://github.com/xxiao053/strategy-agent-lab)**。

[GitHub Free 支持公开仓库使用 Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)。项目网址格式为 `https://<owner>.github.io/<repository>/`，无需购买域名；自定义域名是可选项。

当前 [Pages 限额](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)包括：网站体积最多 1 GB、每月流量软限制 100 GB、部署超时 10 分钟。Pages 用于静态项目网站，不是商业交易服务或收费 SaaS 后台。本项目静态查看器不发送凭据、不调用模型；GitHub 本身会按其隐私政策记录访客 IP。

## 不发布也能本地预览

在项目根目录执行：

```sh
pnpm --dir web install --frozen-lockfile
pnpm --dir web build:showcase-preview
pnpm --dir web exec vite preview --outDir dist-showcase-preview --host 127.0.0.1
```

打开 Vite 输出的本地地址。这只构建静态文件，不创建 GitHub 仓库、不上传内容、不调用模型。这套前端流程使用 Node.js 22 和 pnpm 11.25.0；浏览静态产物不需要 Docker。

## 在 GitHub 检查与发布

随附的[工作流程](../../.github/workflows/pages.yml)**只能手动启动**；推送代码或提交 Pull Request 不会自动发布网站。

1. 完成源码、凭据、案例和分发权限检查后，创建或使用已确认的公开 GitHub 仓库，只上传经过检查的源码。
2. 在 **Actions → Review or publish static showcase → Run workflow** 中保持 **publish** 关闭。任务安装固定依赖、运行前端测试、构建 `web/dist-showcase/`，并上传名为 `github-pages` 的待检查产物。源码链接自动取自运行该流程的仓库。
3. 部署前检查该产物。Pages 的上传路径不是整个仓库，不应包含数据库、密钥或私有归档。静态文件均可被访客下载，包括页面当前未显示的打包记录。
4. 批准发布后，在 **Settings → Pages → Build and deployment → Source** 中选择 **GitHub Actions**。检查 `github-pages` 环境的部署规则，使用默认分支；账号支持时可设置人工审核者。
5. 在批准的分支上再次手动运行，打开 **publish**。部署任务必须等待构建成功，只有它获得 `pages: write` 和 `id-token: write` 权限。部署输出会给出实际网站地址。

流程使用 GitHub 临时令牌／OIDC，不需要个人访问令牌或模型密钥。可参考 [GitHub 自定义工作流说明](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)。本地构建成功不等于已在 GitHub 执行或公开上线。

## 分享网址前检查

- 验证项目子路径中的导航与刷新，包括直接打开 `#/project/...`。资源使用相对地址、导航使用哈希，不需要服务器路由或自定义 404 回退。
- 打开两个构建项目、源码、结果、图表和视频，确认源码／本地运行入口指向已确认仓库和指南。
- 确认没有本地 `/api` 请求、模型请求或密钥表单。不要把模型密钥放入 `VITE_*` 变量，这些值可能成为公开 JavaScript。
- 构建产物保留 `LICENSE`、`THIRD_PARTY_NOTICES.txt` 和两份数据说明。[数据说明](../../DATA_NOTICE.zh-CN.md)区分来源与许可；引用来源不等于完成权利核查。

后续更新仍使用同一套手动检查／发布流程。日后关闭网站，也不能收回别人已经下载的文件。
