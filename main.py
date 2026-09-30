import asyncio
import json
import os
import urllib.request
import websockets
import google.generativeai as genai

import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. Firebase Admin SDK 설정 (Firestore 연동)
# ==========================================
FIREBASE_CONFIG = {
    "type": "service_account",
    "project_id": "chuli-game",
    "private_key_id": "61014cfc1498efa2889f1c09314f00aff1f62d6f",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDO2H56TOI16zhf\nattqfZJ2W/P8bPeeL9N4mXtRJ5ypSxb+jHZoY5EOsZ2j3BRxKgx1uw7GJBOHcQ9F\n8D7xCTyXH/m0aMfHLroclIFX1sIjhQtS59tAyA3uSnyMBJSuPFCy6dObaThgMVI0\nTxLj6/jLUHuQtoQAulBbH+671OVBqb01qVojbFnMEntbduQzBUC+d9H4evkLM2pq\nuLXBFvmMbLAmJrdC36mRtosxaYB93CF3MsoeO3ba0koAPDJZMgGDTudAAKR3SnEz\n7PkiVHLGUJctyiY19scJCMwrSeBuiSe94R2jBxkhcxPjyBJhA0pYDuuH8l9pb+pF\nKMMOPxEtAgMBAAECggEADHqc3XWwULlxVrcEfXRi9tdjAmUekUFoZtu3nV9K68nB\nyDdNg3cSTsp3bLsqfo30tNDwD2h+HHXn39EiiE8wLnE5kuFJauJjobVx54ySJ4DE\n0fUhUf4KcnMK+DWPNMMjHpAjJI/2Bz5NK9EOHjMOePxQ4BuqyL0fe509vWuW2Ihb\nGM4+OKIkRO8ZorMTmhHutpvQWmefuZHXWv2qGXFdjGugTQo+ueUcp6w0rt5Tx4xz\nzjWnNjLoOSpec2Ydiup7k4inm+IX2sY4uO+zDZdCMPAjCdtywhEjUttHGCVB0EDB\nVWjMOi0FNcu2IgBUVkyVYWGv7V0bpiewtVPURuvdoQKBgQDn6WvxzDq7AHFTZuGJ\nfLUgTaoZ1IeXlO3Pa2Ee0kF6il41iQAZsJsAAdvXpkv+DbzQDfvEQNo8Pf0zvw7H\nst9MV4ZRPhGcDIoTIyM6U0HaZqc6Akrn44SM2AGKZYnSkj45UY1fQ+zsBlz0YW3Y\nHEoPZjtod9cm1kJx6W2cDC/9sQKBgQDkVI85jtIUyBv3ZalfxkgiN/FjAVK7+hqY\ntbOceQHIqUFQFfHZz0VI9k3oKtienzM/f3VTYHl+HiX4aQvyL3IGOQfulFM2w1em\nUvnEVjZh1/6ow0P7Pi0d3WwX3UYdtlBgE4zSAJ6zH36LI0YD7SWuXqa4Hrnk6kiv\nA8I2vzr+PQKBgCdikvx7jLXZe2WIoWDyFuinh+3fFDAAEOsa92F+n7Qp75nz7Fpw\njcJQjn9vNJSuzJQg69MGmImGlYvGNMJhdF7Itnzxp5fy4TgizYbIQPTQXjIR1ZrQ\nHuC0hn50hBWI1JxzZyj4pjHnWr3+FeOP2lwHJqu1PorP9HTYCc9omnXhAoGBANba\nrw9lUlAV4SMSeafS6Cuy4qTcKOMTvJU4XbP+tewBQKFAlRz1CmhWxQaT0tSoT8wP\nfvKfFJPVgLtY9dHGTZCHd+xLjGY6uK6c48SZr4CwhER/weeYIVI5+i4WnJT26nkN\nzHQL+0nod+YrogWt0Mhc7prQ5vH+d7igW8+ycKutAoGAORW16BwRr6qnTQYB3Xg3\nuxLnoVkJtrdQE1wQKGrpCMEK4X8VUP/gC1xspbTen2TeurCDpIZtn6eYRmq8HaAt\nzJDtC3pQJnCQZkK86fB9lGxqaN1fEFzLlASVHJSCJmG60HokvOvBW3hvfL4XMHec\nYFh7ZxfZuoiGV7XhXK8ACcg=\n-----END PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk-fbsvc@chuli-game.iam.gserviceaccount.com",
    "client_id": "106013153900687003269",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40chuli-game.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CONFIG)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ==========================================
# 2. 시스템 기본 정보 및 API 설정
# ==========================================
CONFIG_URL = "https://raw.githubusercontent.com/damjun0804-cell/dodam_game/refs/heads/main/game_config.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6L5Kt-myAILHI6q8IBy2bYvDl049W-e8PPlMHwacNobEA")
SPOON_AUTH_TOKEN = os.getenv("SPOON_AUTH_TOKEN", "Bearer eyJraWQiOiJ3U2w3bm9kMHVSVDB0OVo3Y1d5ODJYUUxzU0FianM3SVFDckFkcmxUU21vIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOjU3Mzg0MzMsImRpZCI6Im1vemlsbGEvNS4wKHdpbmRvd3NudDEwLjA7d2luNjQ7eDY0KWFwcGxld2Via2l0LzUzNy4zNihraHRtbCxsaWtlZ2Vja28pY2hyb21lLzE1MC4wLjAuMHdoYWxlLzQuMzkuNDEwLjE0c2FmYXJpLzUzNy4zNiIsImNudHJ5Ijoia3IiLCJleHAiOjE3OTA3NjQzOTYsImdyYW50IjpbImF1dGgiXSwiaWF0IjoxNzkwNzQ5OTk2fQ.NAn3V6qyC8q5motgAw1wUNWcIbkYKyFWE-A8eHpf_o2qSDTxKlWJBxZ0xzgECR3cQpTuZ6qGc20ge2WCQ5naPZ6z4JYdl5ClLtmVRKH70zFnYQTnBHyIiKsoaWsUo8WR5ZSEIkLCp_udZ5G8wpQgswt6B8GUKgd0B04yjfuuvkowSSpfR8QPCHgZ9hyeJM8RQ19xs1t4AwAxTatkfb5LcqOfImlNDukOxSqlD729rtygANFUPE67JSe2arD8IgvCPgmutKk_5o7At1kFDPfjHq1uUb2HdP9LlZ_yh0hLY3GR3N2gPKN8sWF3poA7PVR8y4F7FB2kIFUbtr38VfzwQw")
SPOON_LIVE_ID = os.getenv("SPOON_LIVE_ID", "6199801")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

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
# 4. GitHub Raw JSON 실시간 동기화
# ==========================================
def fetch_remote_config():
    global current_config
    try:
        req = urllib.request.Request(CONFIG_URL, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
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
# 5. Gemini 1.5 Flash AI 답변 생성
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
async def spoon_chat_handler():
    websocket_url = f"wss://kor-live.spooncast.net/api/v2/lives/{SPOON_LIVE_ID}/sockets/"
    headers = {"Authorization": SPOON_AUTH_TOKEN, "User-Agent": "Mozilla/5.0"}

    # websockets 패키지 호환성을 위한 구/신버전 파라미터 처리
    connect_kwargs = {"headers": headers}
    try:
        async with websockets.connect(websocket_url, **connect_kwargs) as ws:
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
    except TypeError:
        # 구버전 websockets 호환 처리 (extra_headers)
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
# 8. 메인 실행 루프
# ==========================================
async def main_loop():
    fetch_remote_config()
    await asyncio.gather(
        config_sync_loop(),
        spoon_chat_handler()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n[INFO] 추리 게임 봇이 종료되었습니다.")
