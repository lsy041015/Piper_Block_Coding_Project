#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Piper 블록 코딩 — GUI 런처
터미널 없이 서버를 시작하고 브라우저를 자동으로 열어주는 데스크탑 앱
"""
import os, sys, time, signal, threading, subprocess, webbrowser
import tkinter as tk
import urllib.request

APP_DIR    = os.path.dirname(os.path.abspath(__file__))
SERVER_PY  = os.path.join(APP_DIR, "server.py")
SERVER_URL = "http://127.0.0.1:5000"

# ── 다크 테마 (web app과 동일) ──────────────────────────────────
BG     = "#0b0f16"
CARD   = "#141a24"
BORDER = "#2a3550"
TEXT   = "#e2e8f0"
MUTED  = "#64748b"
BLUE   = "#3b82f6"
GREEN  = "#22c55e"
RED    = "#ef4444"
AMBER  = "#f59e0b"


def _get_icon_path():
    """아이콘 경로 반환 — install_app.py 가 생성한 icon.png 사용"""
    return os.path.join(APP_DIR, "icon.png")


def _is_server_running():
    """Piper Flask 앱이 포트 5000에서 실행 중인지 확인"""
    try:
        resp = urllib.request.urlopen(SERVER_URL + "/", timeout=1)
        return resp.headers.get("X-Piper-App") == "block-coding"
    except Exception:
        return False


class PiperLauncher:
    def __init__(self):
        self.server_proc = None
        self._anim_on    = False
        self._loading    = False
        self._build_window()

    # ── UI 구성 ─────────────────────────────────────────────────
    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("Piper 블록 코딩")
        self.root.geometry("370x195")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        # 창 아이콘
        icon_path = _get_icon_path()
        try:
            img = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, img)
            self._icon_img = img          # GC 방지
        except Exception:
            pass

        # 헤더
        hdr = tk.Frame(self.root, bg=CARD, pady=11)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🤖  Piper 블록 코딩",
                 fg=TEXT, bg=CARD,
                 font=("Noto Sans KR", 13, "bold")).pack()

        # 구분선
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # 상태 영역
        sf = tk.Frame(self.root, bg=BG, pady=16)
        sf.pack(fill="x", padx=22)

        self.dot = tk.Label(sf, text="●", fg=AMBER, bg=BG,
                            font=("Arial", 13))
        self.dot.grid(row=0, column=0, padx=(0, 9))

        self.status_var = tk.StringVar(value="서버 시작 중...")
        tk.Label(sf, textvariable=self.status_var,
                 fg=TEXT, bg=BG,
                 font=("Noto Sans KR", 11)).grid(row=0, column=1, sticky="w")

        tk.Label(sf, text=SERVER_URL,
                 fg=MUTED, bg=BG,
                 font=("Courier New", 9)).grid(row=1, column=1, sticky="w", pady=(3, 0))

        # 구분선
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # 버튼 영역
        bf = tk.Frame(self.root, bg=CARD, pady=12)
        bf.pack(fill="x")

        self.ide_btn = self._btn(bf, "블록 코딩 IDE",
                                 lambda: webbrowser.open(SERVER_URL),
                                 BLUE, state="disabled")
        self.ide_btn.pack(side="left", padx=(18, 6))

        self.dash_btn = self._btn(bf, "대시보드",
                                  lambda: webbrowser.open(SERVER_URL + "/dashboard"),
                                  "#0f766e", state="disabled")
        self.dash_btn.pack(side="left", padx=6)

        self._btn(bf, "종료", self._quit, RED).pack(side="right", padx=(6, 18))

    @staticmethod
    def _btn(parent, text, cmd, color, state="normal"):
        return tk.Button(parent, text=text, command=cmd, state=state,
                         bg=color, fg="white",
                         activebackground=color, activeforeground="white",
                         font=("Noto Sans KR", 10, "bold"),
                         relief="flat", padx=13, pady=7,
                         cursor="hand2", bd=0)

    # ── 서버 시작 ───────────────────────────────────────────────
    def _start(self):
        # 이미 실행 중인 서버가 있으면 재사용
        if _is_server_running():
            self.root.after(0, self._on_ready, True)
            return

        self._loading = True
        self._animate_dot()

        def _run():
            self._stderr_buf = []
            self.server_proc = subprocess.Popen(
                [sys.executable, SERVER_PY],
                cwd=APP_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,   # 독립 프로세스 그룹
            )
            def _read_err():
                for raw in self.server_proc.stderr:
                    line = raw.decode(errors="replace").rstrip()
                    self._stderr_buf.append(line)
                    if len(self._stderr_buf) > 50:
                        self._stderr_buf.pop(0)
            threading.Thread(target=_read_err, daemon=True).start()
            # 준비 대기 (최대 20초)
            for _ in range(40):
                if _is_server_running():
                    self.root.after(0, self._on_ready, False)
                    return
                time.sleep(0.5)
            self.root.after(0, self._on_failed)

        threading.Thread(target=_run, daemon=True).start()

    def _animate_dot(self):
        """서버 시작 중 점 깜박임 애니메이션"""
        if not self._loading:
            return
        self._anim_on = not self._anim_on
        self.dot.config(fg=AMBER if self._anim_on else MUTED)
        self.root.after(500, self._animate_dot)

    def _on_ready(self, reused=False):
        self._loading = False
        self.dot.config(fg=GREEN)
        self.status_var.set("서버 실행 중" + ("  (기존 프로세스 재사용)" if reused else ""))
        self.ide_btn.config(state="normal")
        self.dash_btn.config(state="normal")
        webbrowser.open(SERVER_URL)

    def _on_failed(self):
        self._loading = False
        self.dot.config(fg=RED)
        hint = self._stderr_buf[-1] if getattr(self, "_stderr_buf", []) else ""
        msg = f"서버 시작 실패: {hint}" if hint else "서버 시작 실패 — server.py 확인 필요"
        self.status_var.set(msg)

    # ── 종료 ────────────────────────────────────────────────────
    def _quit(self):
        if self.server_proc and self.server_proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.server_proc.pid), signal.SIGTERM)
                self.server_proc.wait(timeout=3)
            except Exception:
                try:
                    self.server_proc.kill()
                except Exception:
                    pass
        self.root.destroy()

    def run(self):
        self.root.after(100, self._start)   # UI 그린 뒤 서버 시작
        self.root.mainloop()


if __name__ == "__main__":
    PiperLauncher().run()
