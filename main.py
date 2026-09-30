import asyncio
import json
import os
import re
import urllib.request
import websockets
import google.generativeai as genai

# ==========================================
# 1. 사용자 설정값 및 환경변수 반영
# ==========================================
CONFIG_URL = "https://raw.githubusercontent.com/damjun0804-cell/dodam_game/refs/heads/main/game_config.json"

# Gemini API Key (환경 변수 또는 직접 입력)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

# 스푼라디오 로그인 토큰
SPOON_AUTH_TOKEN = "Bearer eyJraWQiOiJ3U2w3bm9kMHVSVDB0OVo3Y1d5ODJYUUxzU0FianM3SVFDckFkcmxUU21vIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOjU3Mzg0MzMsImRpZCI6Im1vemlsbGEvNS4wKHdpbmRvd3NudDEwLjA7d2luNjQ7eDY0KWFwcGxld2Via2l0LzUzNy4zNihraHRtbCxsaWtlZ2Vja28pY2hyb21lLzE1MC4wLjAuMHdoYWxlLzQuMzkuNDEwLjE0c2FmYXJpLzUzNy4zNiIsImNudHJ5Ijoia3IiLCJleHAiOjE3OTA3NjQzOTYsImdyYW50IjpbImF1dGgiXSwiaWF0IjoxNzkwNzQ5OTk2fQ.NAn3V6qyC8q5motgAw1wUNWcIbkYKyFWE-A8eHpf_o2qSDTxKlWJBxZ0xzgECR3cQpTuZ6qGc20ge2WCQ5naPZ6z4JYdl5ClLtmVRKH70zFnYQTnBHyIiKsoaWsUo8WR5ZSEIkLCp_udZ5G8wpQgswt6B8GUKgd0B04yjfuuvkowSSpfR8QPCHgZ9hyeJM8RQ19xs1t4AwAxTatkfb5LcqOfImlNDukOxSqlD729rtygANFUPE67JSe2arD8IgvCPgmutKk_5o7At1kFDPfjHq1uUb2HdP9LlZ_yh0hLY3GR3N2gPKN8sWF3poA7PVR8y4F7FB2kIFUbtr38VfzwQw"

# 스푼라디오 사용자 ID (@ 뒤의 아이디 입력)
SPOON_USER_HANDLE = "kpz17o"

# Gemini API 설정
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# 전역 게임 설정 변수
current_config = {}

# ==========================================
# 2. @아이디 기반으로 실시간 방송 ID 가져오기
# ==========================================
def get_live_id_from_handle(handle: str) -> str:
    """사용자 핸들(@kpz17o)을 기반으로 현재 진행 중인 방송의 LIVE ID 숫자를 조회"""
    try:
        url = f"https://kor-api.spooncast.net/users/username/{handle}/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Authorization": SPOON_AUTH_TOKEN})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            results = data.get("results", [])
            if results:
                user_id = results[0].get("id")
                # 유저 정보를 기반으로 현재 방송 조회
                live_url = f"https://kor-api.spooncast.net/users/{user_id}/live/"
                live_req = urllib.request.Request(live_url, headers={"User-Agent": "Mozilla/5.0", "Authorization": SPOON_AUTH_TOKEN})
                with urllib.request.urlopen(live_req) as live_resp:
                    live_data = json.loads(live_resp.read().decode('utf-8'))
                    live_id = live_data.get("results", [{}])[0].get("id")
                    if live_id:
                        return str(live_id)
    except Exception as e:
        print(f"[WARNING] 자동 방송 ID 조회 실패 (수동 ID 적용 필요): {e}")
    return None

# ==========================================
# 3. GitHub Raw JSON 실시간 동기화
# ==========================================
def fetch_remote_config():
    global current_config
    try:
        req = urllib.request.Request(
            CONFIG_URL, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            current_config = data
            print("[INFO] GitHub 설정 실시간 동기화 완료")
    except Exception as e:
        print(f"[ERROR] GitHub 설정 로드 실패: {e}")

async def config_sync_loop():
    while True:
        fetch_remote_config()
        await asyncio.sleep(5)

# ==========================================
# 4. Gemini 1.5 Flash AI 답변 생성
# ==========================================
def generate_ai_response(user_name: str, message: str) -> str:
    if not current_config.get("is_game_active", True):
        return "현재 추리게임이 일시 정지된 상태입니다."

    target_word = current_config.get("target_word", "")
    forbidden_words = current_config.get("forbidden_words", [])
    system_instruction = current_config.get("system_instruction", "")
    suspects = current_config.get("suspects", {})

    target_suspect = None
    for key, suspect in suspects.items():
        if f"용의자{key}" in message or (suspect.get("name") and suspect.get("name") in message):
            target_suspect = suspect
            break

    if target_suspect:
        prompt = f"""
        [역할 부여] 당신은 추리게임 용의자 '{target_suspect.get('name')}'입니다.
        [용의자 프로필] 성격: {target_suspect.get('personality')}, 알리바이: {target_suspect.get('alibi')}, 비밀: {target_suspect.get('secret')}
        [규칙] 정답: {target_word}, 금지어: {', '.join(forbidden_words)}, 지침: {system_instruction}
        [질문] 시청자 '{user_name}': "{message}"
        [응답] 성격을 연기하여 1~2문장으로 간결하게 답하세요. 정답 및 금지어는 절대 말하지 마세요.
        """
    else:
        prompt = f"""
        [역할 부여] 당신은 추리게임 진행자 AI입니다.
        [규칙] 정답: {target_word}, 금지어: {', '.join(forbidden_words)}, 지침: {system_instruction}
        [질문] 시청자 '{user_name}': "{message}"
        [응답] 1~2문장의 유용한 힌트를 제공하세요. 정답 및 금지어는 언급 금지.
        """

    try:
        response = model.generate_content(prompt)
        answer = response.text.strip()
        for word in forbidden_words:
            if word and word in answer:
                return "AI가 답변 중 금지어를 감지하여 답변을 취소했습니다. 다시 질문해 주세요!"
        return answer
    except Exception as e:
        print(f"[ERROR] Gemini API 오류: {e}")
        return "AI 답변 생성 중 오류가 발생했습니다."

# ==========================================
# 5. 스푼라디오 웹소켓 핸들러
# ==========================================
async def spoon_chat_handler(live_id: str):
    websocket_url = f"wss://kor-live.spooncast.net/api/v2/lives/{live_id}/sockets/"
    headers = {"Authorization": SPOON_AUTH_TOKEN, "User-Agent": "Mozilla/5.0"}

    async with websockets.connect(websocket_url, extra_headers=headers) as ws:
        print(f"[SUCCESS] 스푼라디오 라이브 웹소켓 연결 완료 (Live ID: {live_id})")

        while True:
            try:
                raw_data = await ws.recv()
                data = json.loads(raw_data)

                if data.get("event") == "live_message":
                    user_name = data.get("user", {}).get("nickname", "시청자")
                    message = data.get("message", "").strip()

                    if message.startswith("!"):
                        command = message[1:].strip()
                        print(f"[{user_name}] 명령어 수신: {command}")

                        ai_response = generate_ai_response(user_name, command)
                        formatted_reply = f"🤖 @{user_name}: {ai_response}"

                        send_packet = {"action": "send_message", "message": formatted_reply}
                        await ws.send(json.dumps(send_packet))

            except websockets.ConnectionClosed:
                print("[WARNING] 웹소켓 연결이 종료되었습니다.")
                break
            except Exception as e:
                print(f"[ERROR] 메시지 처리 중 오류: {e}")

# ==========================================
# 6. 메인 실행부
# ==========================================
async def main():
    fetch_remote_config()
    
    # @kpz17o 핸들 기반으로 현재 켜진 방송의 Live ID 자동 수집
    print(f"[INFO] '@{SPOON_USER_HANDLE}' 님의 방송 라이브 ID를 조회 중...")
    live_id = get_live_id_from_handle(SPOON_USER_HANDLE)
    
    if not live_id:
        print("[ERROR] 방송 ID를 찾을 수 없습니다. 방송이 켜져 있는지 확인하거나 F12에서 Live ID를 직접 입력해 주세요.")
        return

    print(f"[INFO] 라이브 ID 수집 완료: {live_id}")
    
    await asyncio.gather(
        config_sync_loop(),
        spoon_chat_handler(live_id)
    )

if __name__ == "__main__":
    asyncio.run(main())
