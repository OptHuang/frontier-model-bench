# 接入个人主页

这个项目保持为独立静态站，个人主页只需要链接到它，不需要把抓取脚本或 `node_modules` 带进 Hugo 仓库。

## 外链（推荐起步方式）

```html
<a href="https://opthuang.github.io/frontier-model-bench/">
  Frontier Model Bench →
</a>
```

## iframe（希望保留在主页视觉流中时）

```html
<iframe
  src="https://opthuang.github.io/frontier-model-bench/"
  title="Frontier Model Bench"
  loading="lazy"
  style="width:100%; min-height:960px; border:0; border-radius:16px;"
></iframe>
```

iframe 适合展示，但会牺牲站点导航、分享 URL 和移动端高度控制；正式接入前应在个人主页的浅色/深色主题中各检查一次。若以后需要同域路径，可把本仓库构建产物复制到 Hugo 的 `static/benchmarks/`，仍然让本仓库负责数据更新。

