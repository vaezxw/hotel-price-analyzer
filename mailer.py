# -*- coding: utf-8 -*-
"""
导出后邮件发送：QQ 邮箱 SMTP（授权码）附带 Excel。
配置：data/mail_settings.json（勿外传）。
"""
from __future__ import annotations

import json
import mimetypes
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import config

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "smtp_host": "smtp.qq.com",
    "smtp_port": 465,
    "use_ssl": True,
    "username": "",
    "password": "",
    "from_addr": "",
    "to_addrs": [],
    "subject_prefix": "酒店房价导出",
}


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def parse_recipients(raw) -> list[str]:
    """接受 list 或逗号/分号/空白分隔字符串。"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw]
    else:
        items = re.split(r"[,;，；\s]+", str(raw).strip())
    out: list[str] = []
    seen: set[str] = set()
    for addr in items:
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(addr)
    return out


def normalize_settings(data: dict | None = None) -> dict[str, Any]:
    cfg = dict(_DEFAULTS)
    if data:
        cfg.update({k: data[k] for k in _DEFAULTS if k in data})
    cfg["enabled"] = bool(cfg.get("enabled"))
    cfg["use_ssl"] = bool(cfg.get("use_ssl", True))
    try:
        cfg["smtp_port"] = int(cfg.get("smtp_port") or 465)
    except (TypeError, ValueError):
        cfg["smtp_port"] = 465
    cfg["username"] = str(cfg.get("username") or "").strip()
    cfg["password"] = str(cfg.get("password") or "").strip()
    cfg["from_addr"] = str(cfg.get("from_addr") or "").strip() or cfg["username"]
    cfg["to_addrs"] = parse_recipients(cfg.get("to_addrs"))
    cfg["smtp_host"] = str(cfg.get("smtp_host") or "smtp.qq.com").strip()
    cfg["subject_prefix"] = str(cfg.get("subject_prefix") or "酒店房价导出").strip()
    return cfg


def load_settings(path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else config.MAIL_SETTINGS_PATH
    if not path.is_file():
        return normalize_settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return normalize_settings()
        return normalize_settings(data)
    except (OSError, json.JSONDecodeError):
        return normalize_settings()


def save_settings(settings: dict, path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else config.MAIL_SETTINGS_PATH
    cfg = normalize_settings(settings)
    _ensure_parent(path)
    path.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return cfg


def settings_ready(settings: dict | None = None) -> tuple[bool, str]:
    """检查能否发信（不要求 enabled）。返回 (ok, reason)。"""
    cfg = normalize_settings(settings) if settings is not None else load_settings()
    if not cfg["username"]:
        return False, "未填写发件 QQ 邮箱"
    if not _EMAIL_RE.match(cfg["username"]):
        return False, "发件邮箱格式不正确"
    if not cfg["password"]:
        return False, "未填写授权码（不是 QQ 登录密码）"
    if not cfg["to_addrs"]:
        return False, "未填写收件人"
    for addr in cfg["to_addrs"]:
        if not _EMAIL_RE.match(addr):
            return False, f"收件人格式不正确：{addr}"
    if not cfg["smtp_host"]:
        return False, "未填写 SMTP 主机"
    return True, ""


def is_mail_ready(settings: dict | None = None) -> bool:
    cfg = normalize_settings(settings) if settings is not None else load_settings()
    if not cfg["enabled"]:
        return False
    ok, _ = settings_ready(cfg)
    return ok


def _attach_file(msg: EmailMessage, path: Path) -> None:
    data = path.read_bytes()
    ctype, encoding = mimetypes.guess_type(str(path))
    if ctype is None or encoding is not None:
        ctype = "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)
    msg.add_attachment(
        data,
        maintype=maintype,
        subtype=subtype,
        filename=path.name,
    )


def send_export_mail(
    paths: list[Path | str],
    *,
    subject: str | None = None,
    body: str | None = None,
    settings: dict | None = None,
) -> None:
    """发送带附件邮件；失败抛异常。"""
    cfg = normalize_settings(settings) if settings is not None else load_settings()
    ok, reason = settings_ready(cfg)
    if not ok:
        raise ValueError(reason)

    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            files.append(path)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not subject:
        names = "、".join(f.name for f in files) if files else "（无附件）"
        subject = f"{cfg['subject_prefix']} {stamp}"
        if len(subject) > 180:
            subject = f"{cfg['subject_prefix']} {stamp}"
        _ = names  # kept for potential body use

    if body is None:
        lines = [
            "酒店房价工具自动发送。",
            f"时间：{stamp}",
            "",
            "附件：",
        ]
        if files:
            lines.extend(f"  - {f.name}" for f in files)
        else:
            lines.append("  （无）")
        lines.extend(["", "请勿回复本邮件。"])
        body = "\n".join(lines)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"] or cfg["username"]
    msg["To"] = ", ".join(cfg["to_addrs"])
    msg.set_content(body)
    for f in files:
        _attach_file(msg, f)

    host = cfg["smtp_host"]
    port = int(cfg["smtp_port"])
    if cfg["use_ssl"]:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=60) as smtp:
            smtp.login(cfg["username"], cfg["password"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(cfg["username"], cfg["password"])
            smtp.send_message(msg)


def try_send_export_mail(paths: list[Path | str], *, quiet_if_disabled: bool = True) -> bool:
    """
    导出后调用：未启用则跳过；启用则发信。
    返回是否发送成功；失败只打印，不抛给调用方。
    """
    cfg = load_settings()
    if not cfg["enabled"]:
        if not quiet_if_disabled:
            print("邮件发送：未开启（可在「邮件设置」中开启）")
        return False
    ok, reason = settings_ready(cfg)
    if not ok:
        print(f"邮件发送：已开启但配置不完整 — {reason}")
        return False
    try:
        send_export_mail(paths, settings=cfg)
        print(f"邮件已发送至：{', '.join(cfg['to_addrs'])}")
        return True
    except Exception as e:
        print(f"邮件发送失败（导出文件已保存）：{e}")
        return False
