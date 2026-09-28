#!/usr/bin/env python3
"""repo_probe.py — 采集候选仓库的取证材料。只取证，不做判断。

用法：
  python repo_probe.py <证据目录> github:owner/name [gitee:owner/name ...] [--clone]
  python repo_probe.py search '<关键词>'

每个目标产出 <证据目录>/<平台>-<owner>_<name>/：
  meta.json    原始 API 响应（不丢字段，判断出错可回查）
  meta.txt     归一化摘要（stars / 许可证 / 最近提交 / 归档 / issue）
  tree.txt     目录树（文件总数 / 顶层条目 / 一级目录）
  activity.txt 最近提交日期
  license.txt  LICENSE 原文前 40 行
  deps.txt     依赖清单原文（每份截断 60 行）
  PROBE.md     汇总，subagent 先读这份
  src/         仅 --clone 时存在，附 clone-sha.txt

只依赖 Python 标准库；GitHub 侧有 gh 时优先用 gh（带鉴权，额度更高）。
许可证一律以 LICENSE 原文为准：GitHub 的 license 字段常为 null 或 NOASSERTION。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

DEPS_FILES = [
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts", "requirements.txt",
    "go.mod", "Cargo.toml", "composer.json", "CMakeLists.txt", "pyproject.toml",
    "setup.py", "Gemfile", "mix.exs", "pubspec.yaml",
]
LICENSE_FILES = ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "LICENSE-2.0.txt"]
UA = {"User-Agent": "repo-probe", "Accept": "application/vnd.github+json"}


def fetch(url: str, timeout: int = 30) -> bytes | None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def get_json(url: str, use_gh: bool = False) -> dict | list | None:
    """GitHub 优先走 gh（已鉴权）；否则退回 urllib。"""
    if use_gh:
        try:
            out = subprocess.run(
                ["gh", "api", url.replace("https://api.github.com/", "")],
                capture_output=True, timeout=60,
            )
            if out.returncode == 0 and out.stdout.strip():
                return json.loads(out.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
    raw = fetch(url)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def raw_file(plat: str, repo: str, branch: str, path: str) -> bytes | None:
    url = (f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
           if plat == "github" else f"https://gitee.com/{repo}/raw/{branch}/{path}")
    data = fetch(url)
    if not data:
        return None
    head = data.lstrip()[:1]
    if head in (b"{", b"<"):  # API 报错页 / HTML 404 页，不是文件内容
        return None
    return data


def dig(obj, dotted: str, default=""):
    cur = obj
    for key in dotted.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(key)]
            except (ValueError, IndexError):
                return default
        elif isinstance(cur, dict):
            if key not in cur:
                return default
            cur = cur[key]
        else:
            return default
    return default if cur is None else cur


def probe_one(outdir: str, target: str, clone: bool) -> bool:
    plat, _, repo = target.partition(":")
    if plat not in ("github", "gitee") or "/" not in repo:
        print(f"!! 目标格式应为 github:owner/name 或 gitee:owner/name: {target}", file=sys.stderr)
        return False
    is_gh = plat == "github"
    base = "https://api.github.com" if is_gh else "https://gitee.com/api/v5"
    name = f"{plat}-{repo.replace('/', '_')}"
    d = os.path.join(outdir, name)
    os.makedirs(d, exist_ok=True)
    w = lambda fn, text: open(os.path.join(d, fn), "w", encoding="utf-8").write(text)

    meta = get_json(f"{base}/repos/{repo}", use_gh=is_gh)
    if not isinstance(meta, dict) or dig(meta, "message"):
        print(f"!! {target} 取不到元数据（不存在 / 私有 / 限流）", file=sys.stderr)
        return False
    w("meta.json", json.dumps(meta, ensure_ascii=False, indent=1))

    branch = dig(meta, "default_branch") or "master"
    stars = dig(meta, "stargazers_count") or dig(meta, "stars_count")
    lic_field = dig(meta, "license.spdx_id") or dig(meta, "license.name")
    pushed = dig(meta, "pushed_at") or dig(meta, "updated_at")
    lines = [
        f"repo: {plat}:{dig(meta, 'full_name', repo)}",
        f"url: https://{ 'github' if is_gh else 'gitee' }.com/{repo}",
        f"description: {dig(meta, 'description')}",
        f"language: {dig(meta, 'language')}",
        f"stars: {stars}",
        f"forks: {dig(meta, 'forks_count')}",
        f"archived: {dig(meta, 'archived') or dig(meta, 'is_archived') or False}",
        f"open_issues: {dig(meta, 'open_issues_count')}",
        f"created_at: {dig(meta, 'created_at')}",
        f"pushed_at: {pushed}",
        f"default_branch: {branch}",
        f"api_license_field: {lic_field or '(空)'}  <- 不可信，以 license.txt 为准",
    ]
    w("meta.txt", "\n".join(lines) + "\n")

    tree = get_json(f"{base}/repos/{repo}/git/trees/{branch}?recursive=1", use_gh=is_gh)
    if isinstance(tree, dict):
        items = tree.get("tree") or []
        files = [t.get("path", "") for t in items if t.get("type") == "blob"]
        tops: dict[str, int] = {}
        for p in files:
            tops[p.split("/")[0]] = tops.get(p.split("/")[0], 0) + 1
        out = [f"files: {len(files)}  truncated: {tree.get('truncated', False)}", "", "顶层条目（文件数）:"]
        out += [f"  {k}\t{v}" for k, v in sorted(tops.items(), key=lambda kv: -kv[1])[:40]]
        out += ["", "一级目录:"]
        out += [f"  {t['path']}" for t in items if t.get("type") == "tree" and t.get("path", "").count("/") <= 1]
        w("tree.txt", "\n".join(out) + "\n")

    commits = get_json(f"{base}/repos/{repo}/commits?per_page=20", use_gh=is_gh)
    if isinstance(commits, list):
        dates = [dig(c, "commit.author.date") or dig(c, "commit.committer.date") for c in commits]
        w("activity.txt", "\n".join(x for x in dates if x) + "\n")

    for lf in LICENSE_FILES:
        blob = raw_file(plat, repo, branch, lf)
        if blob:
            w("license.txt", f"(来源: {lf})\n" + blob.decode("utf-8", "replace")[:8000])
            break
    else:
        w("license.txt", "未找到常见许可证文件，需人工确认\n")

    deps = []
    for f in DEPS_FILES:
        blob = raw_file(plat, repo, branch, f)
        if blob:
            body = blob.decode("utf-8", "replace").splitlines()[:60]
            deps.append(f"===== {f} =====\n" + "\n".join(body))
    w("deps.txt", "\n\n".join(deps) + "\n" if deps else "未发现常见依赖清单文件，依赖需从源码或文档判断\n")

    act = open(os.path.join(d, "activity.txt"), encoding="utf-8").read().splitlines()[:5] if os.path.exists(os.path.join(d, "activity.txt")) else []
    lic_head = open(os.path.join(d, "license.txt"), encoding="utf-8").read().splitlines()
    w("PROBE.md", "\n".join([
        f"# 采集摘要 {plat}:{repo}", "",
        f"- 仓库：https://{'github' if is_gh else 'gitee'}.com/{repo}",
        f"- 描述：{dig(meta, 'description') or '（无）'}",
        f"- 主语言：{dig(meta, 'language') or '?'} ｜ Stars：{stars or '?'} ｜ 归档：{dig(meta, 'archived') or dig(meta, 'is_archived') or False} ｜ Open issues：{dig(meta, 'open_issues_count')}",
        f"- 默认分支：{branch} ｜ 最近提交：{pushed or '?'}",
        f"- API license 字段：{lic_field or '空'}  ← 不可信，以 license.txt 原文为准",
        f"- 许可证原文首行：{lic_head[1] if len(lic_head) > 1 else (lic_head[0] if lic_head else '无')}",
        "- 最近提交日期（前 5）：",
        *[f"    {x}" for x in act],
        "", "## 下一步", "", "```bash",
        f"git clone --depth 1 https://{'github' if is_gh else 'gitee'}.com/{repo}.git <临时目录>/src",
        "git -C <临时目录>/src rev-parse HEAD", "```", "",
    ]) + "\n")

    if clone:
        src = os.path.join(d, "src")
        url = f"https://{'github' if is_gh else 'gitee'}.com/{repo}.git"
        try:
            subprocess.run(["git", "clone", "--depth", "1", "-q", url, src], check=True, timeout=600)
            sha = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
            w("clone-sha.txt", sha + "\n")
        except (OSError, subprocess.SubprocessError) as e:
            print(f"!! {target} 克隆失败: {e}", file=sys.stderr)

    print(f"ok  {target} → {d}")
    return True


def search(keyword: str) -> int:
    try:
        out = subprocess.run(
            ["gh", "search", "repos", "--limit", "20", "--json",
             "fullName,description,stargazersCount,language,pushedAt,license", keyword],
            capture_output=True, timeout=90,
        )
        if out.returncode == 0 and out.stdout.strip():
            print(out.stdout.decode("utf-8", "replace"))
            return 0
    except (OSError, subprocess.TimeoutExpired):
        pass
    data = get_json("https://api.github.com/search/repositories?per_page=20&q=" +
                    urllib.request.quote(keyword))
    if isinstance(data, dict) and data.get("items"):
        print(json.dumps([{k: dig(i, k) for k in
                           ("full_name", "description", "stargazers_count", "language", "pushed_at")}
                          for i in data["items"]], ensure_ascii=False, indent=1))
        return 0
    print("搜索失败或无结果（未鉴权时 GitHub 搜索限流严格）", file=sys.stderr)
    print(f"Gitee 搜索接口已失效（恒返回空），Gitee 候选请用 web 搜索: site:gitee.com {keyword}", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "search":
        return search(" ".join(argv[2:]))
    clone = "--clone" in argv
    targets = [a for a in argv[1:] if a != "--clone"]
    outdir = targets.pop(0)
    if not targets:
        print("没有给候选仓库", file=sys.stderr)
        return 2
    os.makedirs(outdir, exist_ok=True)
    ok = all(probe_one(outdir, t, clone) for t in targets)
    print("\n下一步：subagent 先读每个证据目录的 PROBE.md，再决定挖哪些路径。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
