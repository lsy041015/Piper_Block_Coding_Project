#!/usr/bin/env python3
# 파이썬3 인터프리터로 실행하도록 지정하는 shebang 라인
# -*- coding: utf-8 -*-
# 소스 파일의 문자 인코딩을 UTF-8로 지정 (한글 사용 가능)

"""
==========================================================
 Piper 로봇 블록 코딩 백엔드 서버 (server.py)
==========================================================
역할:
  1. 웹 브라우저에서 블록으로 만든 프로그램을 Python 코드로 받아
     실제 Piper 로봇(piper_sdk)에 실행
  2. 실행 중인 로봇 출력(print)을 WebSocket으로 브라우저에 실시간 전송
  3. 브라우저의 정지(Stop) 명령을 받아 실행 중인 프로세스를 종료

실행 방법:
  python3 server.py
  → 브라우저에서 http://localhost:5000 접속
"""

# ── 표준 라이브러리 ──────────────────────────────────────
import os          # 파일 경로 조작, 파일 삭제(unlink) 등 OS 기능
import re          # 정규식 (CAN 포트 검증, 코드 화이트리스트 검증)
import sys         # 현재 Python 인터프리터 경로(sys.executable) 참조
import subprocess  # 외부 프로세스(생성된 Python 코드) 실행 및 관리
import threading   # 출력 스트리밍을 백그라운드 스레드로 처리 (UI 블로킹 방지)
import tempfile    # 실행할 코드를 임시 파일(.py)로 저장
import time        # 대기 및 통신 주기 설정용
import os          # 경로 및 파일 관리 용

# ── 서드파티 라이브러리 ────────────────────────────────────
from flask import Flask, render_template, request, jsonify, send_from_directory
# Flask       : 웹 서버 프레임워크 (HTTP 요청/응답 처리)
# render_template : templates/ 폴더의 HTML 파일을 반환
# request     : 클라이언트가 보낸 JSON 데이터 읽기
# jsonify     : 딕셔너리를 JSON HTTP 응답으로 변환

from flask_socketio import SocketIO
# SocketIO : WebSocket 통신 라이브러리
#            브라우저 ↔ 서버 간 실시간 양방향 통신 (터미널 출력 스트리밍)

# ============================================================ 
# Flask 앱 초기화
# ============================================================
app = Flask(__name__)
# Flask 앱 객체 생성. __name__ 은 현재 모듈 이름으로,
# Flask가 templates/ static/ 폴더 위치를 자동으로 찾는 데 사용됨

# [수정 6] SECRET_KEY를 환경변수에서 읽고, 없으면 랜덤 생성
# → git에 올려도 실제 키가 노출되지 않음
import secrets as _secrets
app.config['SECRET_KEY'] = os.environ.get('PIPER_SECRET_KEY') or _secrets.token_hex(32)

socketio = SocketIO(
    app,
    # 로컬호스트 두 가지 표기 모두 허용 (localhost ↔ 127.0.0.1 불일치 방지)
    # 서버 자체가 127.0.0.1에만 바인딩되므로 외부 접근은 OS 수준에서 차단됨
    cors_allowed_origins=["http://localhost:5000", "http://127.0.0.1:5000"],
    async_mode='threading'
    # Python threading 모드로 비동기 처리 (eventlet/gevent 불필요)
)

current_process = None
SIMULATION_MODE = False  # 시물레이션 모드 여부
# [시물레이션용] 가상 로봇 상태 (CAN 연결 없이 대시보드 업데이트용)
virtual_state = {
    "joints": [0,0,0,0,0,0],
    "pose": [0,250,250,0,0,0],
    "gripper": 0
}

process_lock = threading.Lock()
# current_process에 여러 스레드가 동시에 접근하는 것을 방지하는 뮤텍스 잠금
# with process_lock: 블록 안에서만 프로세스 조작 가능
 
# ============================================================
# SDK 경로 자동 탐지
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# __file__ : 현재 server.py 파일의 경로
# os.path.abspath : 절대 경로로 변환
# os.path.dirname : 파일이 속한 디렉토리 경로 추출
# 결과 예시: /home/wego/piper_ws/src/piper_block_coding

WORKSPACE_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
# 결과 예시: /home/wego/piper_ws

SDK_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', 'piper_sdk'))
# BASE_DIR에서 한 단계 위(..)로 올라간 후 piper_sdk 폴더 경로
# 결과 예시: /home/wego/piper_ws/src/piper_sdk

SCRIPTS_PATH = os.path.join(SDK_PATH, 'scripts')
# piper_sdk 안의 scripts 폴더 (WeGo_MetaClass.py 등이 위치)
# 결과 예시: /home/wego/piper_ws/src/piper_sdk/scripts

# ============================================================
# 생성 코드 헤더 템플릿
# ============================================================
# 블록 코딩으로 만든 사용자 코드 앞에 항상 자동으로 붙는 공통 코드.
# Python의 str.format()으로 {sdk_path}, {scripts_path}, {can_port} 등을
# 실제 값으로 치환하여 사용.
#
# 이 헤더에는:
#   - piper_sdk import 및 로봇 연결
#   - 전역 속도 변수(_speed)
#   - 로봇 제어 함수들 (robot_enable, movej, movep, movel 등)
# 가 포함되어 있어, 사용자 블록 코드에서 바로 호출 가능.
# ---------- 시뮬레이션 전용 헤더 (Mock) ----------
SIM_HEADER_TEMPLATE = '''\
#!/usr/bin/env python3
import time, math, requests
SERVER_URL = "http://127.0.0.1:5000/update_virtual"

_speed       = 20         # 이동 속도 (1~100%)
_gripper_pos = 0.0        # 현재 그리퍼 위치 (mm)
_joints      = [0.0]*6    # 현재 관절 각도 (도) — 내부 추적용
_pose        = [0.0, 250.0, 250.0, 0.0, 0.0, 0.0]  # 현재 포즈 (mm, 도)
_session     = requests.Session()  # TCP 연결 재사용 (20Hz 루프 오버헤드 감소)

# ── 실제 Piper 로봇 기준 최대 속도 (100% 시) ──────────────────
_MAX_JOINT_DPS = 200.0   # 도/초  (관절 최대 각속도)
_MAX_CART_MMPS = 500.0   # mm/초  (직교 이동 최대 속도)
_MAX_ROT_DPS   = 100.0   # 도/초  (직교 자세 최대 각속도)
_MAX_GRIP_MMPS = 60.0    # mm/초  (그리퍼 최대 이동 속도)
_UPDATE_HZ     = 20      # 보간 전송 주기 (Hz) — 20Hz = 50ms/step

def _lerp(a, b, t): return a + (b - a) * t

# DH 파라미터 (Piper 로봇)
_DH_A     = [0, 0, 0.28503, -0.02198, 0, 0]
_DH_ALPHA = [0, -math.pi/2, 0, math.pi/2, -math.pi/2, math.pi/2]
_DH_D     = [0.123, 0, 0, 0.25075, 0, 0.091]
_DH_TOFF  = [0, math.radians(-174.22), math.radians(-100.78), 0, 0, 0]

def _fk(joints_deg):
    """DH 순기구학 → [x(mm), y(mm), z(mm), rx(deg), ry(deg), rz(deg)]"""
    T = [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
    def _mat_mul(A, B):
        R = [[0]*4 for _ in range(4)]
        for i in range(4):
            for j in range(4):
                for k in range(4):
                    R[i][j] += A[i][k] * B[k][j]
        return R
    for i in range(6):
        th = math.radians(joints_deg[i]) + _DH_TOFF[i]
        a, al, d = _DH_A[i], _DH_ALPHA[i], _DH_D[i]
        ct, st, ca, sa = math.cos(th), math.sin(th), math.cos(al), math.sin(al)
        Ti = [[ct, -st*ca,  st*sa, a*ct],
              [st,  ct*ca, -ct*sa, a*st],
              [0,      sa,     ca,    d],
              [0,       0,      0,    1]]
        T = _mat_mul(T, Ti)
    x, y, z = T[0][3]*1000, T[1][3]*1000, T[2][3]*1000
    ry =  math.asin(max(-1.0, min(1.0, -T[2][0])))
    rx =  math.atan2(T[2][1], T[2][2])
    rz =  math.atan2(T[1][0], T[0][0])
    return [round(x,2), round(y,2), round(z,2),
            round(math.degrees(rx),2), round(math.degrees(ry),2), round(math.degrees(rz),2)]

def _send(joints=None, pose=None, gripper=None):
    """서버로 가상 상태 전송 (오류 무시)"""
    data = {}
    if joints  is not None: data["joints"]  = joints
    if pose    is not None: data["pose"]    = pose
    if gripper is not None: data["gripper"] = gripper
    try: _session.post(SERVER_URL, json=data, timeout=0.5)
    except: pass

def _interp_and_send(get_interp, start_val, end_val, duration, extra_data=None):
    """start_val → end_val 을 duration 초 동안 20Hz로 보간하며 전송"""
    if duration <= 0:
        _send(**{**get_interp(end_val), **(extra_data or {})})
        return
    dt    = 1.0 / _UPDATE_HZ
    steps = max(1, int(round(duration * _UPDATE_HZ)))
    t0    = time.time()
    for s in range(1, steps + 1):
        t       = s / steps
        payload = get_interp([_lerp(start_val[i], end_val[i], t) for i in range(len(start_val))])
        if extra_data:
            payload.update(extra_data)
        _send(**payload)
        if s < steps:
            elapsed = time.time() - t0
            sleep_t = s * dt - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

def robot_enable():
    print("[SIM] 로봇 활성화")

def set_speed(s):
    global _speed
    _speed = max(1, min(100, int(s)))
    print(f"[SIM] 속도: {_speed}%")

def movej(j1, j2, j3, j4, j5, j6):
    global _joints, _pose, _gripper_pos
    target    = [float(j1), float(j2), float(j3), float(j4), float(j5), float(j6)]
    max_delta = max(abs(target[i] - _joints[i]) for i in range(6))
    vel       = _MAX_JOINT_DPS * _speed / 100.0
    duration  = max_delta / vel if max_delta > 0.01 else 0.0
    print(f"[SIM] MoveJ {[round(v,1) for v in target]}  ({duration:.2f}초)")
    _interp_and_send(
        lambda v: {"joints": v, "pose": _fk(v)},
        _joints[:], target, duration,
        extra_data={"gripper": _gripper_pos}
    )
    _joints = target[:]
    _pose   = _fk(target)

def movep(x, y, z, rx, ry, rz):
    global _pose, _gripper_pos
    target = [float(x), float(y), float(z), float(rx), float(ry), float(rz)]
    dist   = math.sqrt(sum((target[i] - _pose[i])**2 for i in range(3)))
    rdist  = math.sqrt(sum((target[i] - _pose[i])**2 for i in range(3, 6)))
    t_pos  = dist  / (_MAX_CART_MMPS * _speed / 100.0) if dist  > 0.1 else 0.0
    t_rot  = rdist / (_MAX_ROT_DPS   * _speed / 100.0) if rdist > 0.01 else 0.0
    duration = max(t_pos, t_rot)
    print(f"[SIM] MoveP ({x},{y},{z})  ({duration:.2f}초)")
    _interp_and_send(
        lambda v: {"pose": v},
        _pose[:], target, duration,
        extra_data={"gripper": _gripper_pos}
    )
    _pose = target[:]

def movel(x, y, z, rx, ry, rz):
    """선형 이동 — 시뮬레이션에서는 MoveP와 동일하게 처리"""
    movep(x, y, z, rx, ry, rz)

def gripper_ctrl(g):
    global _gripper_pos
    target   = float(g)
    delta    = abs(target - _gripper_pos)
    vel      = _MAX_GRIP_MMPS * _speed / 100.0
    duration = delta / vel if delta > 0.1 else 0.0
    print(f"[SIM] 그리퍼 {g}mm  ({duration:.2f}초)")
    _interp_and_send(
        lambda v: {"gripper": v[0]},
        [_gripper_pos], [target], duration
    )
    _gripper_pos = target

def go_home():
    import json as _json, os as _os
    try:
        with open(_os.path.join(_os.getcwd(), 'calibration.json')) as _f:
            _j = _json.load(_f).get('joints', [0.0]*6)
    except Exception:
        _j = [0.0]*6
    print(f"[SIM] 홈 위치로 이동: {[round(v,1) for v in _j]}")
    movej(*_j)

def emergency_stop():
    print("[SIM] 비상 정지")

def print_current_pose():
    print(f"[SIM] 현재 포즈: X={_pose[0]:.1f} Y={_pose[1]:.1f} Z={_pose[2]:.1f} "
          f"RX={_pose[3]:.1f} RY={_pose[4]:.1f} RZ={_pose[5]:.1f}")

def print_current_joint():
    print(f"[SIM] 현재 관절: " + " ".join(f"J{i+1}={_joints[i]:.1f}" for i in range(6)))
'''

CODE_HEADER_TEMPLATE = '''\
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# [Piper 블록 코딩으로 생성된 코드]
import sys
import time

# piper_sdk 및 WeGo_MetaClass 경로를 Python 모듈 탐색 경로에 추가
sys.path.insert(0, {sdk_path})
sys.path.insert(0, {scripts_path})
from piper_sdk import C_PiperInterface_V2
from WeGo_MetaClass import WeGo
# WeGo : 단위 변환(convert), 도달 확인(check), 모터 활성화(enable) 기능 제공

print("로봇에 연결 중... (CAN 포트: {can_port_str})")
piper = C_PiperInterface_V2({can_port})
piper.ConnectPort()
wego = WeGo(piper)  # WeGo 메타클래스 초기화 (piper 인터페이스 주입)
print("연결 완료")

_speed = 20  # 기본 이동 속도 (1~100%). set_speed()로 변경 가능
_gripper_pos = 0  # 현재 그리퍼 상태 (mm, 0=닫힘)

# ---------- 공통 제어 함수 ----------
# WeGo의 convert(단위변환), check(도달확인), enable(활성화)을 활용하여
# 각 함수의 핵심 로직을 위임하고, 속도 제어만 직접 처리한다.

def robot_enable():
    """모든 모터 활성화 — WeGo.Enable에 위임"""
    wego.enable.run()

def set_speed(speed):
    """이동 속도 변경 (1~100%). 이후 movej/movep/movel 모두에 적용됨"""
    global _speed
    _speed = max(1, min(100, int(speed)))  # 1~100 범위로 클램핑
    print("속도 설정: " + str(_speed) + "%")

def movej(j1, j2, j3, j4, j5, j6):
    """관절 공간 이동 (MoveJ). 단위: 도°"""
    vals = wego.convert.run([j1, j2, j3, j4, j5, j6, _gripper_pos])
    # WeGo.convert: 도°/mm 값을 SDK 내부 단위(×1000)로 일괄 변환
    joints, g = vals[:6], abs(vals[6])
    print("MoveJ J1=" + str(j1) + " J2=" + str(j2) + " J3=" + str(j3) +
          " J4=" + str(j4) + " J5=" + str(j5) + " J6=" + str(j6))
    piper.MotionCtrl_2(0x01, 0x01, int(_speed), 0x00)
    # 0x01=활성화, 0x01=MoveJ 모드, _speed=속도(1~100), 0x00=예비
    piper.JointCtrl(*joints)
    piper.GripperCtrl(g, 1000, 0x01, 0)
    wego.check.joint(*joints)  # WeGo.check: 모든 관절이 목표에 도달할 때까지 대기

def movep(x, y, z, rx, ry, rz):
    """직교 공간 PTP 이동 (MoveP). 위치: mm, 자세: 도° (최단 경로)"""
    vals = wego.convert.run([x, y, z, rx, ry, rz, _gripper_pos])
    pose, g = vals[:6], abs(vals[6])
    print("MoveP X=" + str(x) + " Y=" + str(y) + " Z=" + str(z) +
          " RX=" + str(rx) + " RY=" + str(ry) + " RZ=" + str(rz))
    piper.MotionCtrl_2(0x01, 0x00, int(_speed), 0x00)
    # 0x00=MoveP(PTP) 모드
    piper.EndPoseCtrl(*pose)
    piper.GripperCtrl(g, 1000, 0x01, 0)
    wego.check.pose(*pose)  # WeGo.check: 엔드 이펙터가 목표 위치에 도달할 때까지 대기

def movel(x, y, z, rx, ry, rz):
    """직교 공간 선형 이동 (MoveL). 위치: mm, 자세: 도° (직선 경로 보장)"""
    vals = wego.convert.run([x, y, z, rx, ry, rz, _gripper_pos])
    pose, g = vals[:6], abs(vals[6])
    print("MoveL X=" + str(x) + " Y=" + str(y) + " Z=" + str(z) +
          " RX=" + str(rx) + " RY=" + str(ry) + " RZ=" + str(rz))
    piper.MotionCtrl_2(0x01, 0x02, int(_speed), 0x00)
    # 0x02=MoveL(선형 보간) 모드
    piper.EndPoseCtrl(*pose)
    piper.GripperCtrl(g, 1000, 0x01, 0)
    wego.check.pose(*pose)

def gripper_ctrl(position_mm):
    """그리퍼 단독 제어 (0mm=완전 닫힘, 70mm=완전 열림)"""
    global _gripper_pos
    _gripper_pos = position_mm
    print("그리퍼: " + str(position_mm) + "mm")
    piper.GripperCtrl(abs(round(float(position_mm) * 1000)), 1000, 0x01, 0)
    time.sleep(0.5)  # 그리퍼 이동 완료 대기

def emergency_stop():
    """비상 정지 — 즉시 모든 모터 정지. 재사용 시 robot_enable() 재호출 필요"""
    piper.MotionCtrl_1(0x01, 0, 0x00)  # 0x01=E-Stop 명령
    print("비상 정지 실행됨")

def go_home():
    """캘리브레이션된 홈 위치 복귀"""
    import json as _json, os as _os
    try:
        with open(_os.path.join(_os.getcwd(), 'calibration.json')) as _f:
            _j = _json.load(_f).get('joints', [0.0]*6)
    except Exception:
        _j = [0.0]*6
    print("홈 위치로 이동 중... " + str([round(v,1) for v in _j]))
    movej(*_j)
    print("홈 위치 도달")

def print_current_pose():
    """현재 위치(직교 공간 좌표) 및 자세 출력"""
    try:
        current_state = piper.GetArmEndPoseMsgs().end_pose
        x = current_state.X_axis / 1000.0
        y = current_state.Y_axis / 1000.0
        z = current_state.Z_axis / 1000.0
        rx = current_state.RX_axis / 1000.0
        ry = current_state.RY_axis / 1000.0
        rz = current_state.RZ_axis / 1000.0
        print("현재 좌표: X=" + str(round(x,1)) + " Y=" + str(round(y,1)) + " Z=" + str(round(z,1)) + " RX=" + str(round(rx,1)) + " RY=" + str(round(ry,1)) + " RZ=" + str(round(rz,1)))
    except Exception as e:
        print("좌표 읽기 실패: " + str(e))

def print_current_joint():
    """현재 관절 각도 출력"""
    try:
        current_state = piper.GetArmJointMsgs().joint_state
        j1 = current_state.joint_1 / 1000.0
        j2 = current_state.joint_2 / 1000.0
        j3 = current_state.joint_3 / 1000.0
        j4 = current_state.joint_4 / 1000.0
        j5 = current_state.joint_5 / 1000.0
        j6 = current_state.joint_6 / 1000.0
        print("현재 관절: J1=" + str(round(j1,1)) + " J2=" + str(round(j2,1)) + " J3=" + str(round(j3,1)) + " J4=" + str(round(j4,1)) + " J5=" + str(round(j5,1)) + " J6=" + str(round(j6,1)))
    except Exception as e:
        print("관절 읽기 실패: " + str(e))

def set_zero_all():
    """전체 관절(1~6) 현재 위치를 영점으로 설정"""
    print("전체 관절 영점 설정 중...")
    for n in range(1, 7):
        piper.JointConfig(joint_num=n, set_zero=0xAE)
        time.sleep(0.1)
    print("전체 관절 영점 설정 완료. 로봇을 재시작해야 적용됩니다.")

def set_zero_joint(joint_num):
    """특정 관절 현재 위치를 영점으로 설정"""
    n = int(joint_num)
    if n < 1 or n > 6:
        print("관절 번호는 1~6 사이여야 합니다.")
        return
    print("관절 " + str(n) + "번 영점 설정 중...")
    piper.JointConfig(joint_num=n, set_zero=0xAE)
    print("관절 " + str(n) + "번 영점 설정 완료. 로봇을 재시작해야 적용됩니다.")

def print_motor_status():
    """6개 모터의 전압/드라이버온도/모터온도/전류/에러 상태 출력"""
    try:
        info = piper.GetArmLowSpdInfoMsgs()
        print("===== 모터 상태 =====")
        for i in range(1, 7):
            m = getattr(info, "motor_" + str(i))
            s = m.foc_status
            errors = []
            if s.voltage_too_low:      errors.append("저전압")
            if s.motor_overheating:    errors.append("모터과열")
            if s.driver_overcurrent:   errors.append("과전류")
            if s.driver_overheating:   errors.append("드라이버과열")
            if s.collision_status:     errors.append("충돌감지")
            if s.driver_error_status:  errors.append("드라이버에러")
            err_str = "/".join(errors) if errors else "정상"
            enabled = "활성화" if s.driver_enable_status else "비활성화"
            print("M" + str(i) + ": " +
                  "전압=" + str(round(m.vol * 0.1, 1)) + "V  " +
                  "드라이버=" + str(m.foc_temp) + "°C  " +
                  "모터=" + str(m.motor_temp) + "°C  " +
                  "전류=" + str(round(m.bus_current * 0.001, 3)) + "A  " +
                  "상태=" + enabled + "  " +
                  "에러=" + err_str)
        print("=====================")
    except Exception as e:
        print("모터 상태 읽기 실패: " + str(e))

def print_motor_temps():
    """6개 모터의 온도만 간략 출력"""
    try:
        info = piper.GetArmLowSpdInfoMsgs()
        print("===== 모터 온도 =====")
        for i in range(1, 7):
            m = getattr(info, "motor_" + str(i))
            print("M" + str(i) + ": 드라이버=" + str(m.foc_temp) + "°C  모터=" + str(m.motor_temp) + "°C")
        print("====================")
    except Exception as e:
        print("온도 읽기 실패: " + str(e))

# ===== 사용자 블록 코드 시작 =====
# (이 아래에 브라우저 블록 코딩으로 생성된 코드가 자동으로 붙음)
'''


# ============================================================
# 보안 검증 함수
# ============================================================

# [보안 1] 허용된 함수 호출 패턴 (Blockly가 생성할 수 있는 함수만 허용)
_ALLOWED_CALLS = re.compile(
    r'^\s*('
    r'robot_enable\s*\(\s*\)'
    r'|go_home\s*\(\s*\)'
    r'|emergency_stop\s*\(\s*\)'
    r'|print_current_pose\s*\(\s*\)'
    r'|print_current_joint\s*\(\s*\)'
    r'|set_zero_all\s*\(\s*\)'
    r'|set_zero_joint\s*\([1-6]\)'
    r'|print_motor_status\s*\(\s*\)'
    r'|print_motor_temps\s*\(\s*\)'
    r'|set_speed\s*\([\d.]+\)'
    r'|movej\s*\([\d\s.,+-]+\)'
    r'|movep\s*\([\d\s.,+-]+\)'
    r'|movel\s*\([\d\s.,+-]+\)'
    r'|gripper_ctrl\s*\([\d.]+\)'
    r'|time\.sleep\s*\([\d.]+\)'
    r'|print\s*\(\s*["\'].*?["\']\s*\)'  # [수정 4] 문자열 리터럴만 허용 (변수/객체 접근 차단)
    r'|for\s+\w+\s+in\s+range\s*\(.+\):'
    r'|while\s+.+:'
    r'|pass'
    r'|\s+'       # 빈 줄 / 들여쓰기
    r')\s*$'
)

def validate_user_code(code: str) -> tuple[bool, str]:
    """사용자 블록 코드의 각 줄이 허용된 패턴인지 검사한다.

    Blockly 생성 코드에 등장할 수 없는 os, subprocess, import 등의
    위험 키워드와 허용되지 않은 함수 호출을 차단한다.

    Returns:
        (True, '') 이면 안전, (False, 이유) 이면 차단
    """
    # 절대 허용하지 않는 위험 단어 및 패턴 (오탐 방지를 위해 정규식 단어 경계 \b 사용)
    BLOCKED_PATTERNS = [
        r'\bimport\b', r'\bexec\b', r'\beval\b', r'\bopen\b', r'\bos\.', r'\bsys\.',
        r'\bsubprocess\b', r'__', r'\bcompile\b', r'\bglobals\b', r'\blocals\b',
        r'\bgetattr\b', r'\bsetattr\b', r'\bdelattr\b', r'\bvars\b', r'\bdir\('
    ]
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, code):
            return False, f"보안 위반 — 허용되지 않는 코드 포함: '{pattern}'"

    # 줄 단위 화이트리스트 검사
    for lineno, line in enumerate(code.splitlines(), start=1):
        stripped = line.strip()
        if stripped == '' or stripped.startswith('#'):
            continue  # 빈 줄·주석은 허용
        if not _ALLOWED_CALLS.match(line):
            return False, f"{lineno}번째 줄에 허용되지 않는 코드: {stripped!r}"

    return True, ''


# [보안 4] CAN 포트 형식 검증 (can0 ~ can9 형식만 허용)
_VALID_CAN_PORT = re.compile(r'^can\d+$')

def validate_can_port(port: str) -> bool:
    """CAN 포트 이름이 'canN' 형식인지 확인한다. (예: can0, can1)"""
    return bool(_VALID_CAN_PORT.match(port))


def build_header(can_port: str) -> str:
    """CODE_HEADER_TEMPLATE의 {플레이스홀더}를 실제 경로/포트 값으로 치환하여 반환

    Args:
        can_port: 사용할 CAN 포트 이름 (예: "can0", "can1")
    Returns:
        치환이 완료된 헤더 문자열 (사용자 코드 앞에 붙임)
    """
    return CODE_HEADER_TEMPLATE.format(
        sdk_path=repr(SDK_PATH),           # 절대 경로를 repr()로 감싸 따옴표 포함
        scripts_path=repr(SCRIPTS_PATH),   # → '/home/wego/.../piper_sdk' 형태
        can_port=repr(can_port),           # → 'can0' 형태 (따옴표 포함)
        can_port_str=can_port,             # → can0 (따옴표 없음, print용)
    )


# ============================================================
# Flask HTTP 라우트 (엔드포인트) 정의
# ============================================================

@app.route('/')
def index():
    """GET / → index.html 반환
    브라우저가 http://localhost:5000 에 접속하면 Blockly UI 페이지를 보여줌
    """
    from flask import make_response
    resp = make_response(render_template('index.html'))
    resp.headers['X-Piper-App'] = 'block-coding'
    return resp


@app.route('/run', methods=['POST'])
def run_code():
    """POST /run → 블록 코딩으로 생성된 Python 코드를 실행

    요청 JSON 형식:
        { "code": "movej(0,0,...)\n...", "can_port": "can0" }

    처리 흐름:
        1. JSON에서 코드와 CAN 포트 추출
        2. 헤더(공통 함수) + 사용자 코드 결합
        3. 임시 .py 파일에 저장
        4. subprocess로 실행 (Python 인터프리터 실행)
        5. 백그라운드 스레드에서 출력을 WebSocket으로 스트리밍
    """
    global current_process
    data = request.json or {}              # 요청 Body를 JSON으로 파싱
    user_code = data.get('code', '').strip()   # 사용자 블록 코드
    can_port  = data.get('can_port', 'can0').strip() or 'can0'  # CAN 포트 (기본: can0)

    if not user_code:
        # 코드가 비어있으면 오류 응답 반환 (실행하지 않음)
        return jsonify({'status': 'error', 'message': '실행할 블록이 없습니다.'})

    # [보안 4] CAN 포트 형식 검증 (can0~can9 외 입력 차단)
    if not validate_can_port(can_port):
        return jsonify({'status': 'error', 'message': f'유효하지 않은 CAN 포트입니다: {can_port!r} (예: can0)'})

    # [보안 1] 사용자 코드 화이트리스트 검증 (허용되지 않은 코드 차단)
    ok, reason = validate_user_code(user_code)
    if not ok:
        return jsonify({'status': 'error', 'message': f'보안 검사 실패 — {reason}'})

    if SIMULATION_MODE:
        full_code = SIM_HEADER_TEMPLATE + user_code
    else:
        full_code = build_header(can_port) + user_code
    # 공통 헤더(로봇 연결+함수 정의) + 사용자 블록 코드를 이어붙임

    with process_lock:
        # 뮤텍스 획득: 동시에 두 개의 프로세스가 실행되는 것을 방지
        if current_process and current_process.poll() is None:
            # poll() is None → 프로세스가 아직 실행 중
            return jsonify({'status': 'error', 'message': '이미 실행 중입니다. 먼저 정지해주세요.'})

        # [수정 7] 임시 파일을 try/finally로 감싸 예외 시에도 반드시 삭제
        tmp = tempfile.NamedTemporaryFile(
            mode='w',          # 쓰기 모드
            suffix='.py',      # 파일 확장자
            delete=False,      # 즉시 삭제하지 않음 (스트리밍 완료 후 삭제)
            encoding='utf-8'   # 한글 코드 지원
        )
        tmp_name = tmp.name    # 경로를 미리 저장 (close 후에도 참조 가능)
        try:
            tmp.write(full_code)
            tmp.close()        # 파일 닫기 (flush 포함)
            current_process = subprocess.Popen(
                [sys.executable, '-u', tmp_name],
                # sys.executable : 현재 실행 중인 Python 인터프리터 경로
                # '-u'           : stdout/stderr 버퍼링 비활성화 (실시간 출력)
                stdout=subprocess.PIPE,    # 표준 출력을 파이프로 캡처
                stderr=subprocess.STDOUT,  # 표준 오류도 표준 출력 파이프로 합침
                text=True,                 # 바이트 대신 문자열로 읽기
                bufsize=1,                 # 라인 버퍼링 (줄 단위로 즉시 전달)
            )
        except Exception as e:
            # Popen 실패 또는 파일 쓰기 실패 시 임시 파일 즉시 삭제
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            return jsonify({'status': 'error', 'message': str(e)})

        # [수정 1] proc를 인수로 전달 — 전역 current_process 직접 참조 제거
        # 스레드 시작 시점의 프로세스 객체를 캡처하여 경쟁 조건(race condition) 방지
        def _stream(proc, tmp_path):
            """백그라운드 스레드 함수: 프로세스 출력을 WebSocket으로 전송"""
            # 최대 실행 시간 설정 (무한 루프 방지, 600초)
            MAX_TIME = 600
            def timeout_handler():
                if proc.poll() is None:
                    proc.kill()
                    socketio.emit('output', {'data': f'⏳ 최대 실행 시간({MAX_TIME}초)을 초과하여 강제 종료되었습니다.'})
            
            timer = threading.Timer(MAX_TIME, timeout_handler)
            timer.start()

            try:
                for line in proc.stdout:
                    # 프로세스가 출력하는 줄을 한 줄씩 읽어
                    socketio.emit('output', {'data': line.rstrip()})
                    # 브라우저에 'output' 이벤트로 실시간 전송
            except Exception:
                pass  # 프로세스 강제 종료 시 스트림 읽기 오류 무시
            finally:
                timer.cancel()                  # 최대 실행 시간 타이머 해지
                # 프로세스가 끝나면 반드시 실행되는 정리 블록
                proc.wait()                     # 캡처된 proc 객체 대기
                rc = proc.returncode            # 종료 코드 (0=정상, 0이외=오류)
                msg = '실행 완료' if rc == 0 else '실행 종료 (코드: ' + str(rc) + ')'
                socketio.emit('done', {'returncode': rc, 'message': msg})
                # 브라우저에 'done' 이벤트 전송 (실행 완료 알림)
                try:
                    os.unlink(tmp_path)         # 임시 .py 파일 삭제
                except Exception:
                    pass

        threading.Thread(
            target=_stream,
            args=(current_process, tmp_name),   # 현재 시점의 proc 객체 전달
            daemon=True
        ).start()
        # daemon=True : 메인 프로세스 종료 시 자동으로 함께 종료됨

    return jsonify({'status': 'ok'})   # 실행 시작 성공 응답


@app.route('/stop', methods=['POST'])
def stop_code():
    """POST /stop → 현재 실행 중인 로봇 프로세스 강제 종료

    처리 흐름:
        1. current_process가 존재하고 실행 중인지 확인
        2. terminate() 호출로 SIGTERM 신호 전송 → 프로세스 종료
        3. WebSocket으로 중지 알림 전송
    """
    global current_process
    with process_lock:
        if current_process and current_process.poll() is None:
            # 실행 중인 프로세스가 있을 때만 종료 시도
            current_process.terminate()
            # [보안 3] SIGTERM 전송 후 3초 대기, 응답 없으면 SIGKILL로 강제 종료
            # terminate()만 사용 시 while True: pass 같은 루프는 좀비로 남을 수 있음
            try:
                current_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                current_process.kill()  # SIGKILL: 즉시 강제 종료
            socketio.emit('output', {'data': '사용자가 프로그램을 중지했습니다.'})
            # 브라우저 터미널에 중지 메시지 표시
    return jsonify({'status': 'ok'})


@app.route('/estop', methods=['POST'])
def estop_script():
    """POST /estop → 0-2. piper_emergency_stop.py 실행"""
    script_file = os.path.join(SCRIPTS_PATH, '0-2. piper_emergency_stop.py')
    if os.path.exists(script_file):
        subprocess.Popen([sys.executable, script_file])
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error', 'message': '파일을 찾을 수 없습니다.'})

@app.route('/erecover', methods=['POST'])
def erecover_script():
    """POST /erecover → 0-3. piper_emergency_restore.py 실행"""
    script_file = os.path.join(SCRIPTS_PATH, '0-3. piper_emergency_restore.py')
    if os.path.exists(script_file):
        subprocess.Popen([sys.executable, script_file])
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error', 'message': '파일을 찾을 수 없습니다.'})

@app.route('/full_code', methods=['POST'])
def full_code():
    """POST /full_code → 헤더 포함 전체 실행 코드 반환 (미리보기/디버깅용)

    요청 JSON: { "code": "...", "can_port": "can0" }
    응답 JSON: { "code": "헤더 + 사용자코드 전체" }
    """
    data = request.json or {}
    user_code = data.get('code', '')
    can_port  = data.get('can_port', 'can0').strip() or 'can0'

    # [수정 5] /run과 동일한 검증 적용 — 우회 경로 차단
    # 실행은 안 되지만 SDK 경로 등 서버 정보가 응답에 포함되므로 검증 필요
    if not validate_can_port(can_port):
        return jsonify({'status': 'error', 'message': f'유효하지 않은 CAN 포트: {can_port!r}'})
    ok, reason = validate_user_code(user_code)
    if not ok:
        return jsonify({'status': 'error', 'message': f'보안 검사 실패 — {reason}'})

    return jsonify({'code': build_header(can_port) + user_code})


@app.route('/dashboard')
def dashboard():
    """GET /dashboard → 실시간 상태 대시보드 반환"""
    return render_template('dashboard.html')

@app.route('/meshes/<path:filename>')
def serve_meshes(filename):
    """로봇 3D 모델(STL) 파일 서빙"""
    mesh_dir = os.path.join(WORKSPACE_PATH, 'src/piper_ros/src/piper_description/meshes')
    return send_from_directory(mesh_dir, filename)

# 실시간 대시보드 모니터 스레드 (내부 상태 저장용)
# ============================================================
dashboard_piper = None
latest_telemetry = {
    "joints": [0,0,0,0,0,0],
    "pose": [0,0,0,0,0,0],
    "gripper": 0,
    "status": "Disconnected"
}

def _monitor_loop():
    global dashboard_piper, latest_telemetry
    if SDK_PATH not in sys.path:
        sys.path.insert(0, SDK_PATH)
    if SCRIPTS_PATH not in sys.path:
        sys.path.insert(0, SCRIPTS_PATH)
    
    try:
        from piper_sdk import C_PiperInterface_V2
    except ImportError:
        print("대시보드 모니터: SDK 로드 실패")
        return

    while True:
        if SIMULATION_MODE:
            # 시뮬레이션 모드: 가상 상태를 소켓으로 즉시 전송
            socketio.emit('dashboard_update', {
                'status': 'Connected',
                'joints': virtual_state["joints"],
                'pose': virtual_state["pose"],
                'gripper': virtual_state["gripper"],
                'mode': 'simulation'
            })
            latest_telemetry.update({**virtual_state, "status": "Connected"})
            time.sleep(0.1)
            continue

        if dashboard_piper is None:
            try:
                dashboard_piper = C_PiperInterface_V2("can0")
                dashboard_piper.ConnectPort()
            except Exception as e:
                socketio.emit('dashboard_update', {'status': 'Error', 'message': f'CAN 연결 대기 (can0): {e}'})
                time.sleep(2)
                continue
                
        try:
            joint_msg = dashboard_piper.GetArmJointMsgs().joint_state
            joints = [
                joint_msg.joint_1 / 1000.0,
                joint_msg.joint_2 / 1000.0,
                joint_msg.joint_3 / 1000.0,
                joint_msg.joint_4 / 1000.0,
                joint_msg.joint_5 / 1000.0,
                joint_msg.joint_6 / 1000.0
            ]
            
            pose_msg = dashboard_piper.GetArmEndPoseMsgs().end_pose
            pose = [
                pose_msg.X_axis / 1000.0, 
                pose_msg.Y_axis / 1000.0,
                pose_msg.Z_axis / 1000.0,
                pose_msg.RX_axis / 1000.0,
                pose_msg.RY_axis / 1000.0,
                pose_msg.RZ_axis / 1000.0
            ]
            
            gripper_msg = dashboard_piper.GetArmGripperMsgs().gripper_state
            gripper = gripper_msg.grippers_angle / 1000.0
            
            socketio.emit('dashboard_update', {
                'status': 'Connected',
                'joints': joints,
                'pose': pose,
                'gripper': gripper
            })
            # [추정/티칭용] 최신 정보 내부 저장
            latest_telemetry.update({
                "status": "Connected",
                "joints": joints,
                "pose": pose,
                "gripper": gripper
            })
        except Exception as e:
            latest_telemetry["status"] = "Error"
            socketio.emit('dashboard_update', {'status': 'Error', 'message': f'데이터 수신 오류: {e}'})
            
        time.sleep(0.1)

@app.route('/capture')
def capture_telemetry():
    """GET /capture → 현재 로봇의 최신 텔레메트리(조인트/포즈)를 JSON으로 반환 (티칭 기능용)"""
    state = dict(latest_telemetry)
    state['mode'] = 'simulation' if SIMULATION_MODE else 'real'
    return jsonify(state)


import json as _json

# ── 원점 캘리브레이션 API ─────────────────────────────────────
CALIBRATION_FILE = os.path.join(BASE_DIR, 'calibration.json')
_CALIB_DEFAULT = {'joints': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 'label': '기본 원점 (모든 관절 0°)'}

def _load_calibration() -> dict:
    try:
        with open(CALIBRATION_FILE, encoding='utf-8') as f:
            data = _json.load(f)
        if isinstance(data.get('joints'), list) and len(data['joints']) == 6:
            return data
    except Exception:
        pass
    return dict(_CALIB_DEFAULT)

def _save_calibration(data: dict):
    with open(CALIBRATION_FILE, 'w', encoding='utf-8') as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/calibration')
def calibration_page():
    """GET /calibration → 원점 캘리브레이션 GUI 페이지"""
    from flask import make_response
    resp = make_response(render_template('calibration.html'))
    resp.headers['X-Piper-App'] = 'block-coding'
    return resp

@app.route('/api/calibration', methods=['GET'])
def get_calibration():
    """현재 저장된 캘리브레이션 반환"""
    return jsonify(_load_calibration())

@app.route('/api/calibration', methods=['POST'])
def save_calibration_route():
    """캘리브레이션 저장"""
    data = request.json or {}
    joints = data.get('joints', [])
    if not isinstance(joints, list) or len(joints) != 6:
        return jsonify({'status': 'error', 'message': '관절 값 6개가 필요합니다.'}), 400
    joints = [max(-175.0, min(175.0, float(v))) for v in joints]
    label  = str(data.get('label', ''))[:100]
    cal = {'joints': joints, 'label': label}
    _save_calibration(cal)
    return jsonify({'status': 'ok', 'calibration': cal})

@app.route('/api/calibration/apply', methods=['POST'])
def apply_calibration_route():
    """캘리브레이션된 홈 위치로 가상 로봇 이동 (시뮬레이션 전용)"""
    cal = _load_calibration()
    joints = cal['joints']
    if SIMULATION_MODE:
        virtual_state['joints'] = joints[:]
        return jsonify({'status': 'ok', 'joints': joints,
                        'message': f'시뮬레이션 홈 적용 완료: {[round(v,1) for v in joints]}'})
    return jsonify({'status': 'warning',
                    'message': '실제 로봇 모드: IDE에서 🏠 홈 위치로 이동 블록을 실행하세요.'})


# ── 로봇 드라이버 영점 설정 API ───────────────────────────────
@app.route('/api/robot/set_zero', methods=['POST'])
def api_set_zero():
    """로봇 모터 드라이버에 현재 위치를 영점으로 설정 (Disable → SetZero → Enable)"""
    if SIMULATION_MODE:
        return jsonify({'status': 'warning', 'message': '시뮬레이션 모드에서는 사용할 수 없습니다.'})
    data = request.json or {}
    joint_num = int(data.get('joint_num', 7))
    if joint_num < 1 or joint_num > 7:
        return jsonify({'status': 'error', 'message': '관절 번호는 1~7(전체) 사이여야 합니다.'})
    try:
        piper.DisableArm(7)
        time.sleep(1.0)
        targets = range(1, 7) if joint_num == 7 else [joint_num]
        for n in targets:
            piper.JointConfig(joint_num=n, set_zero=0xAE)
            time.sleep(0.2)
        piper.EnableArm(7)
        time.sleep(1.0)
        label = '전체 관절' if joint_num == 7 else f'관절 {joint_num}번'
        return jsonify({'status': 'ok', 'message': f'{label} 영점 설정 완료. 로봇을 재시작해야 적용됩니다.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


# ── 마스터/슬레이브 모드 전환 API ─────────────────────────────
@app.route('/api/robot/master_slave', methods=['POST'])
def api_master_slave():
    """마스터(교시)/슬레이브(출력)/일반 모드 전환"""
    if SIMULATION_MODE:
        return jsonify({'status': 'warning', 'message': '시뮬레이션 모드에서는 사용할 수 없습니다.'})
    data = request.json or {}
    mode = data.get('mode', '')
    mode_map = {'master': (0xFA, '마스터(교시 입력) 모드'),
                'slave':  (0xFC, '슬레이브(운동 출력) 모드'),
                'normal': (0x00, '일반 모드')}
    if mode not in mode_map:
        return jsonify({'status': 'error', 'message': '유효하지 않은 모드입니다.'})
    try:
        code, label = mode_map[mode]
        piper.MasterSlaveConfig(code, 0x00, 0x00, 0x00)
        time.sleep(0.3)
        return jsonify({'status': 'ok', 'message': f'{label}로 전환됐습니다.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


# ── 로봇 상태 조회 API ────────────────────────────────────────
@app.route('/api/robot/status', methods=['GET'])
def api_robot_status():
    """현재 로봇 상태(활성화 여부, ctrl_mode 등) 반환"""
    if SIMULATION_MODE:
        return jsonify({'status': 'ok', 'simulation': True})
    try:
        arm = piper.GetArmStatus().arm_status
        info = piper.GetArmLowSpdInfoMsgs()
        enabled = all(
            getattr(info, f'motor_{i}').foc_status.driver_enable_status
            for i in range(1, 7)
        )
        motors = {}
        for i in range(1, 7):
            m = getattr(info, f'motor_{i}')
            motors[f'motor_{i}'] = {
                'enabled': m.foc_status.driver_enable_status,
                'driver_temp': m.foc_temp,
                'motor_temp': m.motor_temp,
                'voltage': round(m.vol * 0.1, 1),
            }
        return jsonify({
            'status': 'ok',
            'enabled': enabled,
            'ctrl_mode': arm.ctrl_mode,
            'arm_status': arm.arm_status,
            'mode_feed': arm.mode_feed,
            'err_code': arm.err_code,
            'motors': motors,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# ── 프로그램 저장/불러오기 API ────────────────────────────────
SAVES_DIR = os.path.join(BASE_DIR, 'saves')
os.makedirs(SAVES_DIR, exist_ok=True)

_SAFE_NAME = re.compile(r'^[\w가-힣\-_ .]+$')

def _safe_save_name(name: str) -> str:
    name = name.strip()[:50]
    if not name or not _SAFE_NAME.match(name):
        raise ValueError('프로그램 이름에 사용할 수 없는 문자가 포함되어 있습니다.')
    return name

@app.route('/api/saves', methods=['GET'])
def list_saves():
    """저장된 프로그램 목록 반환 (최신 순)"""
    saves = []
    for entry in sorted(os.scandir(SAVES_DIR), key=lambda e: e.stat().st_mtime, reverse=True):
        if entry.name.endswith('.xml'):
            saves.append({'name': entry.name[:-4], 'mtime': entry.stat().st_mtime})
    return jsonify(saves)

@app.route('/api/saves', methods=['POST'])
def save_program():
    """프로그램을 이름 붙여 서버에 저장"""
    data = request.json or {}
    try:
        name = _safe_save_name(data.get('name', ''))
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    xml = data.get('xml', '').strip()
    if not xml:
        return jsonify({'status': 'error', 'message': 'XML 데이터가 없습니다.'}), 400
    path = os.path.join(SAVES_DIR, name + '.xml')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return jsonify({'status': 'ok', 'name': name})

@app.route('/api/saves/<path:name>', methods=['GET'])
def load_program(name):
    """저장된 프로그램 XML 반환"""
    try:
        name = _safe_save_name(name)
    except ValueError:
        return jsonify({'status': 'error', 'message': '잘못된 프로그램 이름'}), 400
    path = os.path.join(SAVES_DIR, name + '.xml')
    if not os.path.exists(path):
        return jsonify({'status': 'error', 'message': '저장된 프로그램이 없습니다.'}), 404
    with open(path, encoding='utf-8') as f:
        xml = f.read()
    return jsonify({'status': 'ok', 'name': name, 'xml': xml})

@app.route('/api/saves/<path:name>', methods=['DELETE'])
def delete_program(name):
    """저장된 프로그램 삭제"""
    try:
        name = _safe_save_name(name)
    except ValueError:
        return jsonify({'status': 'error', 'message': '잘못된 프로그램 이름'}), 400
    path = os.path.join(SAVES_DIR, name + '.xml')
    if os.path.exists(path):
        os.unlink(path)
    return jsonify({'status': 'ok'})

@app.route('/toggle_sim', methods=['POST'])
def toggle_sim():
    """시뮬레이션 모드 토글"""
    global SIMULATION_MODE
    SIMULATION_MODE = request.json.get('enable', False)
    return jsonify({'status': 'ok', 'simulation': SIMULATION_MODE})

@app.route('/update_virtual', methods=['POST'])
def update_virtual():
    """가상 로봇 상태 업데이트 (Mock SDK에서 호출)"""
    data = request.json or {}
    if "joints" in data: virtual_state["joints"] = data["joints"]
    if "pose" in data: virtual_state["pose"] = data["pose"]
    if "gripper" in data: virtual_state["gripper"] = data["gripper"]
    return jsonify({'status': 'ok'})

# ============================================================
# 서버 진입점
# ============================================================
if __name__ == '__main__':
    # 이 파일을 직접 실행할 때만 서버 시작
    # (다른 모듈에서 import할 때는 실행되지 않음)
    print("=" * 50)
    print("  Piper 블록 코딩 서버")
    print("  http://localhost:5000 에서 접속하세요")
    print("=" * 50)
    
    # 대시보드 텔레메트리 스레드 가동
    monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
    monitor_thread.start()

    socketio.run(
        app,
        host='127.0.0.1',  # [보안 2] 로컬호스트 전용 — 외부 네트워크 접근 차단
                            # 같은 네트워크의 다른 기기에서 로봇 무단 제어 방지
        port=5000,          # 웹 서버 포트 번호
        debug=False         # 디버그 모드 OFF (코드 변경 시 자동 재시작 비활성)
    )
