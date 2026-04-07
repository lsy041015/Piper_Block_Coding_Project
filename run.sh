#!/bin/bash
# ┌─────────────────────────────────────────────────────────────┐
# │  Piper 블록 코딩 서버 실행 스크립트 (run.sh)                │
# │                                                           │
# │  역할: 의존성 설치 → server.py 실행을 한 번에 처리         │
# │  실행: ./run.sh  (또는 bash run.sh)                       │
# │  종료: Ctrl+C                                             │
# └─────────────────────────────────────────────────────────────┘

set -e
# set -e : 이후 명령어 중 하나라도 오류(exit code != 0)가 발생하면
#          스크립트를 즉시 중단 (오류 무시 방지)

# ── 스크립트 경로 기준으로 작업 디렉토리 설정 ────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# BASH_SOURCE[0] : 현재 실행 중인 스크립트 파일 경로
# dirname        : 파일이 속한 디렉토리 경로 추출
# cd ... && pwd  : 해당 디렉토리의 절대 경로 반환
# 결과: 이 스크립트가 어느 위치에서 실행되든 항상 올바른 경로 사용

cd "$SCRIPT_DIR"
# piper_block_coding/ 디렉토리로 이동
# (requirements.txt, server.py가 이 폴더에 있음)

echo "======================================"
echo "  Piper 블록 코딩 서버"
echo "======================================"

echo "[1/3] 가상환경(venv) 구성 중..."
if [ ! -f "venv/bin/activate" ]; then
    python3 -m venv venv 2>/dev/null || {
        echo "가상환경 생성 모듈 없음. 전역(user) 환경 사용."
        rm -rf venv
    }
fi
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "[2/3] 의존성 설치 중..."
pip3 install -q -r requirements.txt
# pip3           : Python 3용 패키지 설치 도구
# install        : 패키지 설치 명령
# -q             : quiet 모드 (불필요한 출력 최소화)
# -r             : 파일에서 패키지 목록 읽기
# requirements.txt 내용:
#   flask>=2.0         (웹 서버 프레임워크)
#   flask-socketio>=5.0 (WebSocket 지원)

# ── piper_sdk 폴더 존재 여부 확인 ────────────────────────────
SDK_DIR="$SCRIPT_DIR/../piper_sdk"
# piper_block_coding/ 의 상위 폴더(src/)에서 piper_sdk 경로 구성

if [ ! -d "$SDK_DIR" ]; then
    # -d : 해당 경로가 디렉토리로 존재하는지 확인
    # ! -d : 존재하지 않으면 true
    echo "경고: piper_sdk 폴더를 찾을 수 없습니다: $SDK_DIR"
    # 경고만 출력하고 계속 진행 (server.py에서 런타임 오류로 처리됨)
fi

# ── Ctrl+C 종료 시 백그라운드 프로세스 정리 ───────────────────
cleanup() {
    echo ""
    echo "서버를 종료합니다..."
    kill 0 2>/dev/null   # 현재 프로세스 그룹의 모든 자식 프로세스 종료
    wait 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM
# trap : Ctrl+C(SIGINT) 또는 종료 시그널(SIGTERM)을 받으면 cleanup() 실행
# → 백그라운드 브라우저 열기 프로세스도 함께 종료됨

# ── Flask 서버 실행 ───────────────────────────────────────────
echo "[3/3] 서버 시작..."
echo "브라우저에서 http://localhost:5000 으로 접속하세요."
echo "종료: Ctrl+C"
echo "======================================"



python3 server.py
# python3 : Python 3 인터프리터로 server.py 실행
# 서버가 실행되는 동안 이 줄에서 블로킹됨 (Ctrl+C로 종료)
# server.py 가 종료되면 스크립트도 함께 종료됨
