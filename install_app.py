#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Piper 블록 코딩 앱 설치 스크립트
실행하면:
  1. 앱 아이콘(icon.png) 생성
  2. ~/.local/share/applications/ 에 .desktop 파일 등록
  3. ~/Desktop/ 바탕화면 바로가기 생성
"""
import os, sys, stat, shutil

APP_DIR   = os.path.dirname(os.path.abspath(__file__))
LAUNCHER  = os.path.join(APP_DIR, "launcher.py")
ICON_PATH = os.path.join(APP_DIR, "icon.png")
PYTHON    = sys.executable

APPS_DIR    = os.path.expanduser("~/.local/share/applications")
DESKTOP_DIR = os.path.expanduser("~/Desktop")


# ── 1. 아이콘 생성 ─────────────────────────────────────────────
def make_icon():
    try:
        from PIL import Image, ImageDraw
        size = 128
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d    = ImageDraw.Draw(img)

        # 배경 원
        d.ellipse([2, 2, 126, 126], fill=(20, 26, 36, 255))
        d.ellipse([4, 4, 124, 124], outline=(42, 53, 80, 255), width=2)

        # 베이스 플레이트 (타원)
        d.ellipse([30, 94, 98, 114], fill=(42, 53, 80, 255))
        d.ellipse([40, 97, 88, 111], fill=(59, 72, 100, 255))

        # 로봇 암 세그먼트
        # link1: 수직 (베이스~엘보)
        d.rounded_rectangle([54, 60, 74, 98], radius=8, fill=(59, 130, 246, 255))
        # link2: 대각선 (엘보~손목) — 직사각형으로 근사
        d.rounded_rectangle([58, 32, 76, 64], radius=8, fill=(59, 130, 246, 255))
        # link3: 엔드 이펙터 방향
        d.rounded_rectangle([68, 16, 84, 38], radius=6, fill=(96, 165, 250, 255))

        # 관절 구체
        joints = [(64, 98, 8, (96, 165, 250)), (67, 62, 7, (96, 165, 250)), (76, 35, 5, (34, 197, 94))]
        for cx, cy, r, col in joints:
            d.ellipse([cx-r, cy-r, cx+r, cy+r],
                      fill=(*col, 255),
                      outline=(255, 255, 255, 60), width=1)

        # 그리퍼 핑거 2개
        d.rounded_rectangle([72, 10, 80, 22], radius=3, fill=(34, 197, 94, 255))
        d.rounded_rectangle([82, 10, 90, 22], radius=3, fill=(34, 197, 94, 255))

        img.save(ICON_PATH, "PNG")
        print(f"  아이콘 생성: {ICON_PATH}")
    except ImportError:
        print("  PIL 없음 — 아이콘 생략 (system icon 사용)")
    except Exception as e:
        print(f"  아이콘 생성 실패: {e}")


# ── 2. .desktop 파일 내용 ─────────────────────────────────────
DESKTOP_CONTENT = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Piper 블록 코딩
GenericName=로봇 블록 코딩
Comment=Piper 로봇 팔을 블록 코딩으로 제어하는 프로그램
Exec={PYTHON} {LAUNCHER}
Icon={ICON_PATH}
Terminal=false
Categories=Education;Science;
Keywords=robot;piper;block;coding;로봇;블록코딩;
StartupNotify=true
StartupWMClass=launcher
"""


def install_desktop():
    os.makedirs(APPS_DIR, exist_ok=True)
    dest = os.path.join(APPS_DIR, "piper-block-coding.desktop")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(DESKTOP_CONTENT)
    # 실행 권한 부여 (GNOME에서 바로가기로 인식하기 위함)
    os.chmod(dest, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    print(f"  앱 메뉴 등록: {dest}")

    # 데스크탑 DB 갱신
    os.system(f"update-desktop-database {APPS_DIR} 2>/dev/null")

    # 바탕화면 바로가기
    if os.path.isdir(DESKTOP_DIR):
        desk = os.path.join(DESKTOP_DIR, "piper-block-coding.desktop")
        shutil.copy2(dest, desk)
        os.chmod(desk, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
        # GNOME에서 바로가기 신뢰 표시
        os.system(f"gio set '{desk}' metadata::trusted true 2>/dev/null")
        print(f"  바탕화면 바로가기: {desk}")

    # launcher.py 실행 권한
    os.chmod(LAUNCHER, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    print(f"  launcher.py 실행 권한 설정 완료")


# ── 실행 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  Piper 블록 코딩 앱 설치")
    print("=" * 50)
    make_icon()
    install_desktop()
    print()
    print("✅ 설치 완료!")
    print("   앱 메뉴(Super 키) 또는 바탕화면에서")
    print("   'Piper 블록 코딩' 을 실행하세요.")
    print("=" * 50)
