import asyncio
import json
import os
import urllib.request
import websockets
import google.generativeai as genai

import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. 환경 변수 및 설정값 로드
# ==========================================
CONFIG_URL = "https://raw.githubusercontent.com/damjun0804-cell/dodam_game/refs/heads/main/game_config.json"

# 환경변수에서 가져오되, 미설정 시 기본값 적용
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
SPOON_AUTH_TOKEN = os.getenv("SPOON_AUTH_TOKEN", "YOUR_SPOON_AUTH_TOKEN_HERE")
SPOON_LIVE_ID = os.getenv("SPOON_LIVE_ID", "6199801")

# ==========================================
# 2. Firebase Admin SDK 설정
# ==========================================
# Local/Server 환경에 맞춰 serviceAccountKey.json 파일 또는 환경변수를 사용
FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH", "serviceAccountKey.json")

if os.path.exists(FIREBASE_KEY_PATH):
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)
else:
    # 예시: 직접 JSON 사양을 넣을 수 있는 예비 초기화
    try:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": "chuli-game",
            # 필요한 계정 정보를 여기에 명시하거나 JSON 파일 사용 권장
        })
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"[WARN] Firebase 인증 설정 필요: {e}")

db = firestore.client() if firebase_admin._apps else None

# ==========================================
# 3. Gemini API 초기화
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

current_config = {}

# ==========================================
# 4. Firestore 점수 및 순위 처리
# ==========================================
def record_correct_answer(user_nickname: str):
    if not db:
        return
    try:
        doc_ref = db.collection("scores").document(user_nickname)
        doc = doc_ref.get()
        if doc.exists:
            current_score = doc.to_dict().get("score", 0)
            doc_ref.update({"score": current_score + 1})
        else:
            doc_ref.set({"score": 1})
        print(f"[DB SUCCESS] '{user_nickname}' 님 점수 업데이트 완료")
    except Exception as e:
        print(f"[DB ERROR] 점수 저장 실패: {e}")

def get_ranking() -> str:
    if not db:
        return "DB 연동 상태를 확인해 주세요."
    try:
        docs = db.collection("scores").order_by("score", direction=firestore.Query.DESCENDING).limit(10).stream()
        rank_list = [(doc.id, doc.to_dict().get("score", 0)) for doc in docs]

        if not rank_list:
            return "📊 현재까지 정답을 맞힌 명탐정이 없습니다."

        rank_text = "🏆 [명탐정 정답 누적 순위표] 🏆\n"
        for idx, (nickname, count) in enumerate(rank_list, 1):
            rank_text += f"{idx}위: {nickname} ({count}회 성공)\n"
        return rank_text.strip()
    except Exception as e:
        print(f"[DB ERROR] 순위 데이터 로드 실패: {e}")
        return "순위 데이터를 조회하는 중에 오류가 발생했습니다."

# ==========================================
# 5. GitHub Raw JSON 동기화
# ==========================================
def fetch_remote_config():
    global current_config
    try:
        req = urllib.request.Request(CONFIG_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            current_config = json.loads(response.read().decode('utf-8'))
            print("[INFO] GitHub 설정 실시간 동기화 완료")
    except Exception as e:
        print(f"[ERROR] GitHub 설정 로드 실패: {e}")

async def config_sync_loop():
    while True:
        fetch_remote_config()
        await asyncio.sleep(5)

# ==========================================
# 6. Gemini AI 답변 생성
# ==========================================
def generate_ai_response(user_name: str, message: str) -> str:
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
        [역할] 당신은 추리게임 용의자 '{target_suspect.get('name')}'입니다.
        [프로필] 성격: {target_suspect.get('personality')}, 알리바이: {target_suspect.get('alibi')}, 비밀: {target_suspect.get('secret')}
        [규칙] 정답: {target_word}, 금지어: {', '.join(forbidden_words)}, 지침: {system_instruction}
        [질문] 시청자 '{user_name}': "{message}"
        [응답] 성격을 연기하여 1~2문장으로 답하세요. 정답 및 금지어는 절대 말하지 마세요.
        """
    else:
        prompt = f"""
        [역할] 당신은 추리게임 진행자 AI입니다.
        [규칙] 정답: {target_word}, 금지어: {', '.join(forbidden_words)}, 지침: {system_instruction}
        [질문] 시청자 '{user_name}': "{message}"
        [응답] 1~2문장의 유용한 힌트를 제공하세요. 정답 및 금지어 언급 금지.
        """

    try:
        response = model.generate_content(prompt)
        answer = response.text.strip()
        for word in forbidden_words:
            if word and word in answer:
                return "AI가 답변 중 금지어를 감지하여 답변을 취소했습니다."
        return answer
    except Exception as e:
        print(f"[ERROR] Gemini API 오류: {e}")
        return "AI 답변 생성 중 오류가 발생했습니다."

# ==========================================
# 7. 채팅 메시지 처리
# ==========================================
def process_incoming_message(user_name: str, message: str) -> str:
    text = message.strip()

    if text == "!순위":
        return get_ranking()

    if not current_config.get("is_game_active", False):
        return None

    target_word = current_config.get("target_word", "").strip()

    if text.startswith("!정답"):
        user_answer = text[3:].strip()
        if not user_answer:
            return f"@{user_name}님, '!정답 [단어]' 입력 형식으로 제출해 주세요!"

        if user_answer.replace(" ", "").lower() == target_word.replace(" ", "").lower():
            record_correct_answer(user_name)
            current_config["is_game_active"] = False
            return f"🎉 축하합니다! @{user_name}님 정답입니다! (정답: {target_word})\n⏸ 정답자가 나와 추리게임이 일시 정지되었습니다."
        else:
            return f"❌ @{user_name}님, 오답입니다! 다시 추리해보세요."

    if text.startswith("!"):
        query = text[1:].strip()
        ai_reply = generate_ai_response(user_name, query)
        return f"🤖 @{user_name}: {ai_reply}"

    return None

# ==========================================
# 8. 스푼라디오 웹소켓 핸들러
# ==========================================
async def spoon_chat_handler():
    websocket_url = f"wss://kor-live.spooncast.net/api/v2/lives/{SPOON_LIVE_ID}/sockets/"
    headers = {"Authorization": SPOON_AUTH_TOKEN, "User-Agent": "Mozilla/5.0"}

    async with websockets.connect(websocket_url, extra_headers=headers) as ws:
        print(f"[SUCCESS] 스푼라디오 라이브 웹소켓 연결 완료 (LIVE ID: {SPOON_LIVE_ID})")

        while True:
            try:
                raw_data = await ws.recv()
                data = json.loads(raw_data)

                if data.get("event") == "live_message":
                    user_name = data.get("user", {}).get("nickname", "시청자")
                    message = data.get("message", "").strip()

                    reply = process_incoming_message(user_name, message)
                    if reply:
                        send_packet = {"action": "send_message", "message": reply}
                        await ws.send(json.dumps(send_packet))

            except websockets.ConnectionClosed:
                print("[WARNING] 웹소켓 연결이 종료되었습니다.")
                break
            except Exception as e:
                print(f"[ERROR] 메시지 처리 오류: {e}")

# ==========================================
# 9. 메인 실행 루프
# ==========================================
async def main():
    fetch_remote_config()
    await asyncio.gather(
        config_sync_loop(),
        spoon_chat_handler()
    )

if __name__ == "__main__":
    asyncio.run(main())
