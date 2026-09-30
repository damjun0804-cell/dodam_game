import asyncio
import json
import re
import urllib.request
import websockets
import google.generativeai as genai

# ==========================================
# 1. 사용자 설정값 및 토큰 반영
# ==========================================
CONFIG_URL = "https://raw.githubusercontent.com/damjun0804-cell/dodam_game/refs/heads/main/game_config.json"
GEMINI_API_KEY = "AQ.Ab8RN6L5Kt-myAILHI6q8IBy2bYvDl049W-e8PPlMHwacNobEA"

# 스푼라디오 로그인 토큰
SPOON_AUTH_TOKEN = "Bearer eyJraWQiOiJ3U2w3bm9kMHVSVDB0OVo3Y1d5ODJYUUxzU0FianM3SVFDckFkcmxUU21vIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOjU3Mzg0MzMsImRpZCI6Im1vemlsbGEvNS4wKHdpbmRvd3NudDEwLjA7d2luNjQ7eDY0KWFwcGxld2Via2l0LzUzNy4zNihraHRtbCxsaWtlZ2Vja28pY2hyb21lLzE1MC4wLjAuMHdoYWxlLzQuMzkuNDEwLjE0c2FmYXJpLzUzNy4zNiIsImNudHJ5Ijoia3IiLCJleHAiOjE3OTA3NjQzOTYsImdyYW50IjpbImF1dGgiXSwiaWF0IjoxNzkwNzQ5OTk2fQ.NAn3V6qyC8q5motgAw1wUNWcIbkYKyFWE-A8eHpf_o2qSDTxKlWJBxZ0xzgECR3cQpTuZ6qGc20ge2WCQ5naPZ6z4JYdl5ClLtmVRKH70zFnYQTnBHyIiKsoaWsUo8WR5ZSEIkLCp_udZ5G8wpQgswt6B8GUKgd0B04yjfuuvkowSSpfR8QPCHgZ9hyeJM8RQ19xs1t4AwAxTatkfb5LcqOfImlNDukOxSqlD729rtygANFUPE67JSe2arD8IgvCPgmutKk_5o7At1kFDPfjHq1uUb2HdP9LlZ_yh0hLY3GR3N2gPKN8sWF3poA7PVR8y4F7FB2kIFUbtr38VfzwQw"

# 스푼라디오 방송 방 번호 (실제 방송 접속 시 브라우저 주소창 맨 뒤 숫자 입력)
SPOON_LIVE_ID = "여기에_방송_숫자_ID_입력"

# Gemini API 설정
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# 전역 게임 설정 변수
current_config = {}

# ==========================================
# 2. GitHub Raw JSON 실시간 불러오기
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
    """5초마다 GitHub에서 최신 설정을 불러오는 백그라운드 태스크"""
    while True:
        fetch_remote_config()
        await asyncio.sleep(5)

# ==========================================
# 3. Gemini 1.5 Flash AI 힌트/답변 생성 함수
# ==========================================
def generate_ai_response(user_name: str, message: str) -> str:
    if not current_config.get("is_game_active", True):
        return "현재 추리게임이 일시 정지된 상태입니다."

    target_word = current_config.get("target_word", "")
    forbidden_words = current_config.get("forbidden_words", [])
    system_instruction = current_config.get("system_instruction", "")
    suspects = current_config.get("suspects", {})

    # 질문 대상(용의자) 파악
    target_suspect = None
    for key, suspect in suspects.items():
        if f"용의자{key}" in message or (suspect.get("name") and suspect.get("name") in message):
            target_suspect = suspect
            break

    # 프롬프트 조립
    if target_suspect:
        prompt = f"""
        [역할 부여]
        당신은 추리게임의 용의자 중 한 명인 '{target_suspect.get('name')}'입니다.
        
        [용의자 프로필]
        - 성격 및 말투: {target_suspect.get('personality')}
        - 사건 시각 알리바이: {target_suspect.get('alibi')}
        - 숨겨진 비밀 (절대 직접 언급 금지): {target_suspect.get('secret')}
        
        [게임 공통 규칙]
        - 추리 정답: {target_word}
        - 절대 언급하면 안 되는 금지어 목록: {', '.join(forbidden_words)}
        - 지침: {system_instruction}
        
        [시청자 질문]
        시청자 '{user_name}': "{message}"
        
        [응답 조건]
        1. 지정된 성격과 말투를 연기하여 1~2문장의 간결한 대답을 작성하세요.
        2. 정답 단어와 금지어 목록에 포함된 단어는 절대로 직접 언급하거나 유사하게 말하지 마세요.
        """
    else:
        prompt = f"""
        [역할 부여]
        당신은 추리게임의 진행자 AI입니다.
        
        [게임 규칙]
        - 추리 정답: {target_word}
        - 절대 언급하면 안 되는 금지어 목록: {', '.join(forbidden_words)}
        - 지침: {system_instruction}
        
        [시청자 질문]
        시청자 '{user_name}': "{message}"
        
        [응답 조건]
        1. 정답을 맞출 수 있도록 유용한 힌트를 1~2문장의 간결한 텍스트로 제공하세요.
        2. 정답 단어와 금지어 목록에 포함된 단어는 절대로 언급하지 마세요.
        """

    try:
        response = model.generate_content(prompt)
        answer = response.text.strip()

        # 2차 코드 레벨 금지어 검증
        for word in forbidden_words:
            if word and word in answer:
                return "AI가 답변 중 금지어를 감지하여 답변을 취소했습니다. 다시 질문해 주세요!"

        return answer
    except Exception as e:
        print(f"[ERROR] Gemini API 오류: {e}")
        return "AI 답변 생성 중 오류가 발생했습니다."

# ==========================================
# 4. 스푼라디오 웹소켓 핸들러
# ==========================================
async def spoon_chat_handler():
    websocket_url = f"wss://kor-live.spooncast.net/api/v2/lives/{SPOON_LIVE_ID}/sockets/"
    
    headers = {
        "Authorization": SPOON_AUTH_TOKEN,
        "User-Agent": "Mozilla/5.0"
    }

    async with websockets.connect(websocket_url, extra_headers=headers) as ws:
        print(f"[SUCCESS] 스푼라디오 라이브 웹소켓 연결 완료 (Live ID: {SPOON_LIVE_ID})")

        while True:
            try:
                raw_data = await ws.recv()
                data = json.loads(raw_data)

                # 채팅 메시지 이벤트 감지
                if data.get("event") == "live_message":
                    user_name = data.get("user", {}).get("nickname", "시청자")
                    message = data.get("message", "").strip()

                    # '!' 접두사 감지
                    if message.startswith("!"):
                        command = message[1:].strip()
                        print(f"[{user_name}] 명령어 수신: {command}")

                        # AI 답변 생성
                        ai_response = generate_ai_response(user_name, command)
                        formatted_reply = f"🤖 @{user_name}: {ai_response}"

                        # 웹소켓 메시지 발송
                        send_packet = {
                            "action": "send_message",
                            "message": formatted_reply
                        }
                        await ws.send(json.dumps(send_packet))

            except websockets.ConnectionClosed:
                print("[WARNING] 웹소켓 연결이 종료되었습니다. 재연결을 시도합니다...")
                break
            except Exception as e:
                print(f"[ERROR] 메시지 처리 중 오류: {e}")

# ==========================================
# 5. 메인 실행부
# ==========================================
async def main():
    fetch_remote_config()
    await asyncio.gather(
        config_sync_loop(),
        spoon_chat_handler()
    )

if __name__ == "__main__":
    asyncio.run(main())
