# Piper Block Coding Project

Piper 6축 로봇 팔을 코딩 없이 제어할 수 있는 **비주얼 블록 코딩 플랫폼**입니다.
구글 Blockly 엔진을 기반으로 블록을 조립하면 Python 코드가 자동 생성되어 실제 로봇에 실행됩니다.

A **visual block coding platform** for controlling the Piper 6-DOF robot arm without writing code.
Built on Google Blockly — assembling blocks auto-generates Python code that runs directly on the real robot.

---

## 주요 구성 요소 / Key Components

| 파일 / File | 역할 / Role |
|-------------|-------------|
| `server.py` | Flask 백엔드 서버 — 코드 실행, WebSocket 스트리밍 / Flask backend — code execution, WebSocket streaming |
| `templates/index.html` | 블록 코딩 IDE 웹 인터페이스 / Block coding IDE web interface |
| `templates/dashboard.html` | 실시간 로봇 모니터링 대시보드 / Real-time robot monitoring dashboard |
| `templates/calibration.html` | 홈 위치 캘리브레이션 페이지 / Home position calibration page |
| `launcher.py` | tkinter GUI 런처 (터미널 없이 실행) / tkinter GUI launcher (no terminal needed) |
| `install_app.py` | 데스크탑 앱 설치 스크립트 / Desktop app installation script |

---

## 핵심 기능 / Core Features

### 1. 블록 코딩 IDE / Block Coding IDE
- `http://localhost:5000` 접속
- 구글 Blockly v9.3.3 엔진 사용 / Powered by Google Blockly v9.3.3
- `MoveJ`, `MoveP`, `MoveL`, `GripperCtrl`, `SetSpeed` 등 로봇 전용 블록 제공
- 블록 → Python 코드 자동 변환 및 실시간 미리보기 / Automatic block → Python code conversion with live preview
- 작성한 프로그램 저장/불러오기 지원 / Program save/load support

### 2. 실시간 실행 & 터미널 출력 / Real-time Execution & Terminal Output
- 생성된 Python 코드를 `subprocess`로 실행 / Generated Python code executed via `subprocess`
- 로봇 출력(print)을 WebSocket으로 브라우저에 실시간 스트리밍 / Robot stdout streamed live to the browser over WebSocket
- 실행 중 즉시 정지(Stop) 기능 / Instant Stop button during execution

### 3. 시뮬레이션 모드 / Simulation Mode
- 실제 CAN 포트 연결 없이 가상 로봇으로 동작 검증 가능 / Test programs without a physical robot or CAN connection
- DH 순기구학으로 관절 → 3D 포즈 실시간 계산 (20Hz 보간) / DH forward kinematics computes 3D pose from joint angles in real-time (20 Hz interpolation)
- 대시보드에 가상 로봇 상태 반영 / Virtual robot state reflected on the dashboard

### 4. 실시간 대시보드 / Real-time Dashboard
- `http://localhost:5000/dashboard` 접속
- Three.js 기반 3D 로봇 시각화 (STL 모델 렌더링) / Three.js 3D robot visualization (STL model rendering)
- 6축 관절 각도, 직교 좌표 포즈, 그리퍼 상태 실시간 표시 / Live display of 6-axis joint angles, Cartesian pose (XYZ + RPY), and gripper state
- 실제 로봇 / 시뮬레이션 모드 연결 상태 표시 / Connection status indicator (Real / Simulation / Error)

### 5. 데스크탑 런처 / Desktop Launcher
- tkinter GUI로 터미널 없이 서버 시작 및 브라우저 자동 오픈 / tkinter GUI starts the server and auto-opens the browser — no terminal required
- `.desktop` 파일로 Linux 앱 메뉴에 등록 가능 / Registers as a Linux desktop app via `.desktop` file

### 6. 보안 / Security
- 생성 코드 화이트리스트 검증 (허용된 함수 외 실행 차단) / Whitelist validation on generated code (blocks only allowed functions)
- CORS를 `localhost:5000`으로 제한 / CORS restricted to `localhost:5000`
- `SECRET_KEY` 환경변수 관리 / `SECRET_KEY` managed via environment variable

---

## 설치 및 실행 / Installation & Run

```bash
# 의존성 설치 / Install dependencies
pip install -r requirements.txt

# 서버 실행 / Run server
python3 server.py

# 또는 GUI 런처 실행 / Or run GUI launcher
python3 launcher.py
```

브라우저에서 `http://localhost:5000` 접속 / Open `http://localhost:5000` in your browser.

---

## 기술 스택 / Tech Stack

`Python 3` · `Flask` · `Flask-SocketIO` · `Google Blockly` · `Three.js` · `Socket.IO` · `tkinter` · `piper_sdk`
