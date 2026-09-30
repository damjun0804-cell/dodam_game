import asyncio
import json
import os
import urllib.request
import websockets

from google import genai
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. Firebase Admin SDK 설정
# ==========================================
# 환경 변수에 FIREBASE_SERVICE_ACCOUNT_JSON 경로 또는 JSON 문자열이 지정된 경우 해당 정보 사용
FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH", "serviceAccountKey.json")

if not firebase_admin._apps:
    if os.path.exists(FIREBASE_KEY_PATH):
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    else:
        # 파일이 없을 시 기존 딕셔너리 구조 참조(환경 변수로 관리 권장)
        FIREBASE_CONFIG = {
            "type": "service_account",
            "project_id": "chuli-game",
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID", ""),
            "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace('\\n', '\n'),
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL", ""),
            "client_id": os.getenv("FIREBASE_CLIENT_ID", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "universe_domain": "googleapis.com"
        }
        cred = credentials.Certificate(FIREBASE_CONFIG)
        firebase_admin.initialize_app(cred)

db = firestore.client()

# ==========================================
# 2. 시스템 기본 정보 및 API 설정
# ==========================================
CONFIG_URL = "https://raw.githubusercontent.com/damjun0804-cell/dodam_game/refs/heads/main/game_config.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SPOON_LIVE_IDS = ["6199801", "42961606"]

ai_client = genai.Client(api_key=GEMINI_API_KEY)

current_config = {}

# ==========================================
# 3. Firestore 데이터베이스 처리
# ==========================================
def record_correct_answer(user_nickname: str):
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
# 4. GitHub Raw JSON 실시간 동기화 (비동기 스레드 동기화)
# ==========================================
def _fetch_remote_config_sync():
    global current_config
    try:
        req = urllib.request.Request(CONFIG_URL, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            current_config = data
            print("[INFO] GitHub 설정 실시간 동기화 완료")
    except Exception as e:
        print(f"[ERROR] GitHub 설정 로드 실패: {e}")

async def fetch_remote_config():
    await asyncio.to_thread(_fetch_remote_config_sync)

async def config_sync_loop():
    while True:
        await fetch_remote_config()
        await asyncio.sleep(5)

# ==========================================
# 5. Gemini AI 답변 생성
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
        response = ai_client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        answer = response.text.strip()
        for word in forbidden_words:
            if word and word in answer:
                return "AI가 답변 중 금지어를 감지하여 답변을 취소했습니다."
        return answer
    except Exception as e:
        print(f"[ERROR] Gemini API 오류: {e}")
        return "AI 답변 생성 중 오류가 발생했습니다."

# ==========================================
# 6. 채팅 메시지 및 정답/명령어 처리
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
# 7. 스푼라디오 웹소켓 핸들러
# ==========================================
async def connect_spoon_websocket(websocket_url, headers):
    try:
        return await websockets.connect(websocket_url, additional_headers=headers)
    except TypeError:
        try:
            return await websockets.connect(websocket_url, extra_headers=headers)
        except TypeError:
            return await websockets.connect(websocket_url)

async def spoon_chat_handler(live_id: str):
    websocket_url = f"wss://kor-live.spooncast.net/api/v2/lives/{live_id}/sockets/"

    while True:
        # GitHub 설정에서 최신 토큰 확인 -> 없으면 환경 변수 참조
        token = current_config.get("spoon_auth_token") or os.getenv("SPOON_AUTH_TOKEN", "")
        
        if not token:
            print(f"[WARNING] SPOON_AUTH_TOKEN이 설정되지 않았습니다. 대시보드에서 토큰을 저장하세요. (5초 후 재시도)")
            await asyncio.sleep(5)
            continue

        headers = {
            "Authorization": token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            print(f"[CONNECTING] 웹소켓 연결 시도 중... (LIVE ID: {live_id})")
            ws = await connect_spoon_websocket(websocket_url, headers)
            async with ws:
                print(f"[SUCCESS] 스푼라디오 라이브 웹소켓 연결 완료 (LIVE ID: {live_id})")

                while True:
                    # 토큰이 중간에 업데이트된 경우 연결 재설정을 위해 확인
                    latest_token = current_config.get("spoon_auth_token") or os.getenv("SPOON_AUTH_TOKEN", "")
                    if latest_token and latest_token != token:
                        print(f"[INFO] SPOON_AUTH_TOKEN이 변경되었습니다. 웹소켓 재연결 진행 중...")
                        break

                    try:
                        raw_data = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(raw_data)

                        if data.get("event") == "live_message":
                            user_name = data.get("user", {}).get("nickname", "시청자")
                            message = data.get("message", "").strip()

                            reply = process_incoming_message(user_name, message)
                            if reply:
                                send_packet = {"action": "send_message", "message": reply}
                                await ws.send(json.dumps(send_packet))
                    except asyncio.TimeoutError:
                        continue

        except (websockets.ConnectionClosed, OSError) as e:
            print(f"[WARNING] 웹소켓 연결 끊김 (LIVE ID: {live_id}): {e}. 5초 후 재연결합니다.")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[ERROR] 웹소켓 오류 발생 (LIVE ID: {live_id}): {e}. 5초 후 재연결합니다.")
            await asyncio.sleep(5)

# ==========================================
# 8. 메인 실행 루프
# ==========================================
async def main_loop():
    await fetch_remote_config()
    
    tasks = [config_sync_loop()]
    for live_id in SPOON_LIVE_IDS:
        tasks.append(spoon_chat_handler(live_id))

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n[INFO] 추리 게임 봇이 종료되었습니다.")
