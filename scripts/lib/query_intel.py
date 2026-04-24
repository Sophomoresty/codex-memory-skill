from __future__ import annotations

import re
from typing import Any


MAX_CJK_TERMS = 12
GENERIC_CJK_QUERY_TERMS = {
    "读取",
    "记忆",
    "查看",
    "查询",
    "一个",
    "这个",
    "那个",
    "最后",
    "想要",
    "问题",
    "什么",
    "怎么",
    "如何",
    "可以",
    "时候",
    "之后",
    "以前",
    "然后",
    "还是",
    "已经",
    "没有",
    "需要",
    "关于",
    "但是",
    "因为",
    "所以",
    "如果",
    "就是",
    "可能",
    "应该",
    "现在",
    "之前",
    "一下",
    "一些",
    "的话",
    "不是",
    "那些",
    "这些",
    "通过",
    "使用",
    "进行",
    "处理",
    "操作",
    "相关",
    "失败",
    "报错",
    "异常",
    "出现",
    "显示",
}

CJK_EN_SYNONYM_MAP = {
    "修补": ["patch", "fix", "repair"],
    "修复": ["patch", "fix", "repair"],
    "文件": ["file"],
    "浏览器": ["browser"],
    "网页": ["web", "page", "browser"],
    "清理": ["clean", "cleanup", "clear"],
    "空间": ["space", "disk"],
    "安装": ["install", "setup"],
    "配置": ["config", "configure", "setup"],
    "删除": ["delete", "remove", "clean"],
    "搜索": ["search", "find", "grep"],
    "替换": ["replace", "substitute"],
    "脚本": ["script"],
    "执行": ["execute", "run", "exec"],
    "调试": ["debug"],
    "编译": ["compile", "build"],
    "部署": ["deploy"],
    "测试": ["test"],
    "备份": ["backup"],
    "恢复": ["restore", "recover"],
    "找回": ["recover", "recovery", "restore"],
    "更新": ["update", "upgrade"],
    "下载": ["download"],
    "上传": ["upload"],
    "监控": ["monitor", "watch"],
    "日志": ["log"],
    "数据库": ["database", "db"],
    "网络": ["network", "net"],
    "端口": ["port"],
    "代理": ["proxy", "agent"],
    "密钥": ["key", "secret", "token"],
    "证书": ["certificate", "cert"],
    "环境": ["env", "environment"],
    "变量": ["variable", "var"],
    "窗口": ["window"],
    "终端": ["terminal", "shell"],
    "命令": ["command", "cmd"],
    "系统": ["system"],
    "服务": ["service", "server"],
    "项目": ["project"],
    "线程": ["thread"],
    "会话": ["session"],
    "聊天": ["chat", "session", "thread"],
    "聊天记录": ["chat", "session", "thread", "history"],
    "记录": ["record", "history"],
    "目录": ["directory", "dir", "folder"],
    "切换": ["switch", "toggle"],
    "启动": ["start", "launch", "boot"],
    "停止": ["stop", "kill"],
    "重启": ["restart", "reload"],
    "同步": ["sync"],
    "迁移": ["migrate"],
    "转换": ["convert", "transform"],
    "分析": ["analyze", "analysis"],
    "报告": ["report"],
    "截图": ["screenshot", "capture"],
    "识别": ["detect", "recognize", "ocr"],
    "输入": ["input", "type"],
    "点击": ["click"],
    "复制": ["copy"],
    "粘贴": ["paste"],
}


def normalized_text(value: Any) -> str:
    if isinstance(value, list):
        return " | ".join(str(item) for item in value)
    return str(value)


def search_normalize(value: Any) -> str:
    text = normalized_text(value).lower()
    text = re.sub(r"[_/.\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_query_terms(query: str) -> tuple[list[str], list[str], list[str]]:
    english_terms = list(dict.fromkeys(re.findall(r"[a-z0-9]{2,}", search_normalize(query))))
    raw_symbol_terms = re.findall(r"[a-zA-Z0-9_.\-/]{3,}", query)
    symbol_terms = list(
        dict.fromkeys(
            term.lower()
            for term in raw_symbol_terms
            if any(marker in term for marker in ("_", ".", "/", "-"))
        )
    )
    cjk_terms: list[str] = []
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        chunk_candidates: list[str] = [chunk]
        for size in (2, 3, 4):
            if len(chunk) < size:
                continue
            for start in range(0, len(chunk) - size + 1):
                candidate = chunk[start : start + size]
                if candidate not in chunk_candidates:
                    chunk_candidates.append(candidate)
        for candidate in chunk_candidates:
            if candidate not in cjk_terms:
                cjk_terms.append(candidate)
            if len(cjk_terms) >= MAX_CJK_TERMS:
                break
        if len(cjk_terms) >= MAX_CJK_TERMS:
            break
    if len(cjk_terms) > 1:
        filtered = [term for term in cjk_terms if term not in GENERIC_CJK_QUERY_TERMS]
        if filtered:
            cjk_terms = filtered
    expanded_en: list[str] = []
    for cjk in cjk_terms:
        for synonym in CJK_EN_SYNONYM_MAP.get(cjk, []):
            if synonym not in english_terms and synonym not in expanded_en:
                expanded_en.append(synonym)
    english_terms = english_terms + expanded_en
    return english_terms, cjk_terms, symbol_terms


def flatten_query_terms(query: str, *, limit: int | None = None) -> list[str]:
    english_terms, cjk_terms, symbol_terms = extract_query_terms(query)
    ordered: list[str] = []
    for term in [*english_terms, *cjk_terms, *symbol_terms]:
        cleaned = search_normalize(term)
        if cleaned and cleaned not in ordered:
            ordered.append(cleaned)
        if limit is not None and len(ordered) >= limit:
            break
    return ordered if limit is None else ordered[:limit]


def overlap_metrics(left_terms: list[str], right_terms: list[str]) -> dict[str, float]:
    left = {search_normalize(term) for term in left_terms if search_normalize(term)}
    right = {search_normalize(term) for term in right_terms if search_normalize(term)}
    if not left or not right:
        return {
            "shared_terms": [],
            "jaccard": 0.0,
            "left_coverage": 0.0,
            "right_coverage": 0.0,
            "overlap": 0.0,
        }
    shared = sorted(left & right)
    jaccard = len(shared) / max(len(left | right), 1)
    left_coverage = len(shared) / max(len(left), 1)
    right_coverage = len(shared) / max(len(right), 1)
    return {
        "shared_terms": shared,
        "jaccard": round(jaccard, 4),
        "left_coverage": round(left_coverage, 4),
        "right_coverage": round(right_coverage, 4),
        "overlap": round(max(jaccard, left_coverage, right_coverage), 4),
    }
