# -*- coding: utf-8 -*-
"""邮件设置窗口：QQ 邮箱 SMTP 导出后自动发送。"""
from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

import mailer


class MailWindow(ctk.CTkToplevel):
    def __init__(self, master, *, log_fn):
        super().__init__(master)
        self.title("邮件设置")
        self.geometry("560x520")
        self.minsize(520, 480)
        self.transient(master)

        self._log = log_fn
        self._build()
        self._load()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(150, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self)
        body.grid(row=0, column=0, sticky="nsew", padx=16, pady=12)
        body.grid_columnconfigure(1, weight=1)

        tip = (
            "用于导出成功后自动发送 Excel（分析表 + 业务汇总）。\n"
            "QQ 邮箱需使用「授权码」，不是登录密码。\n"
            "获取：QQ 邮箱网页 → 设置 → 账户 → 开启 SMTP 服务 → 生成授权码。"
        )
        ctk.CTkLabel(body, text=tip, justify="left", wraplength=480, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12)
        )

        self.enabled_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            body, text="导出后自动发送邮件", variable=self.enabled_var
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        row = 2
        fields = [
            ("发件 QQ 邮箱", "username", False),
            ("授权码", "password", True),
            ("收件人（多个用逗号分隔）", "to_addrs", False),
            ("SMTP 主机", "smtp_host", False),
            ("SMTP 端口", "smtp_port", False),
            ("邮件主题前缀", "subject_prefix", False),
        ]
        self._entries: dict[str, ctk.CTkEntry] = {}
        for label, key, is_pwd in fields:
            ctk.CTkLabel(body, text=label, anchor="w").grid(
                row=row, column=0, sticky="w", padx=(0, 8), pady=6
            )
            entry = ctk.CTkEntry(body, width=320, show="*" if is_pwd else "")
            entry.grid(row=row, column=1, sticky="ew", pady=6)
            self._entries[key] = entry
            row += 1

        self.ssl_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(body, text="使用 SSL（QQ 默认勾选，端口 465）", variable=self.ssl_var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=8
        )
        row += 1

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        ctk.CTkButton(btns, text="保存", width=100, command=self._on_save).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            btns, text="发送测试邮件", width=120, command=self._on_test
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btns, text="关闭", width=80, fg_color="gray40", hover_color="gray30",
            command=self.destroy,
        ).pack(side="right")

    def _load(self):
        cfg = mailer.load_settings()
        self.enabled_var.set(bool(cfg.get("enabled")))
        self.ssl_var.set(bool(cfg.get("use_ssl", True)))
        self._entries["username"].delete(0, "end")
        self._entries["username"].insert(0, cfg.get("username") or "")
        self._entries["password"].delete(0, "end")
        self._entries["password"].insert(0, cfg.get("password") or "")
        to_addrs = cfg.get("to_addrs") or []
        if isinstance(to_addrs, list):
            to_text = ", ".join(to_addrs)
        else:
            to_text = str(to_addrs)
        self._entries["to_addrs"].delete(0, "end")
        self._entries["to_addrs"].insert(0, to_text)
        self._entries["smtp_host"].delete(0, "end")
        self._entries["smtp_host"].insert(0, cfg.get("smtp_host") or "smtp.qq.com")
        self._entries["smtp_port"].delete(0, "end")
        self._entries["smtp_port"].insert(0, str(cfg.get("smtp_port") or 465))
        self._entries["subject_prefix"].delete(0, "end")
        self._entries["subject_prefix"].insert(
            0, cfg.get("subject_prefix") or "酒店房价导出"
        )

    def _collect(self) -> dict:
        return {
            "enabled": bool(self.enabled_var.get()),
            "username": self._entries["username"].get().strip(),
            "password": self._entries["password"].get().strip(),
            "from_addr": self._entries["username"].get().strip(),
            "to_addrs": self._entries["to_addrs"].get().strip(),
            "smtp_host": self._entries["smtp_host"].get().strip() or "smtp.qq.com",
            "smtp_port": self._entries["smtp_port"].get().strip() or "465",
            "use_ssl": bool(self.ssl_var.get()),
            "subject_prefix": self._entries["subject_prefix"].get().strip()
            or "酒店房价导出",
        }

    def _on_save(self):
        raw = self._collect()
        cfg = mailer.normalize_settings(raw)
        if cfg["enabled"]:
            ok, reason = mailer.settings_ready(cfg)
            if not ok:
                messagebox.showerror("配置不完整", reason, parent=self)
                return
        mailer.save_settings(cfg)
        self._log(
            f"[邮件] 已保存设置（自动发送：{'开' if cfg['enabled'] else '关'}）"
        )
        messagebox.showinfo("已保存", "邮件设置已保存。", parent=self)

    def _on_test(self):
        raw = self._collect()
        cfg = mailer.normalize_settings(raw)
        ok, reason = mailer.settings_ready(cfg)
        if not ok:
            messagebox.showerror("无法发送", reason, parent=self)
            return
        try:
            mailer.send_export_mail(
                [],
                subject=f"{cfg['subject_prefix']} 测试",
                body="这是一封测试邮件。若收到说明 SMTP 配置正确。",
                settings=cfg,
            )
        except Exception as e:
            messagebox.showerror("发送失败", str(e), parent=self)
            self._log(f"[邮件] 测试发送失败：{e}")
            return
        self._log(f"[邮件] 测试邮件已发送至：{', '.join(cfg['to_addrs'])}")
        messagebox.showinfo(
            "已发送",
            f"测试邮件已发送至：\n{', '.join(cfg['to_addrs'])}",
            parent=self,
        )
