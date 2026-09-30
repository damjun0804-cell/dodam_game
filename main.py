import asyncio
import json
import httpx
import websockets
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import sqlite3
import openai

app = FastAPI()

# 봇 상태 및 게임 설정 관리용 전역 변수
config_data = {
    "broadcast_id": "",
    "token": "",
    "openai_api_key": ""
}
bot_task = None

class ConfigModel(BaseModel):
    broadcast_id: str
    token: str
    openai_api_key: str = ""

# -------------------------------------------------------------------------
# 데이터베이스 초기화 및 관리 함수
# -------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect("game_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS winners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT,
            user_id TEXT,
            solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_winner(user_name: str, user_id: str):
    conn = sqlite3.connect("game_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO winners (user_name, user_id) VALUES (?, ?)", (user_name, user_id))
    conn.commit()
    conn.close()

def get_ranking_text() -> str:
    """데이터베이스에서 유저별 정답 횟수를 집계하여 순위 텍스트를 생성합니다."""
    conn = sqlite3.connect("game_data.db")
    cursor = conn.cursor()
    # 정답 횟수가 많은 순으로 정렬 (동률일 경우 최근 기록이 빠른 순 등 추가 정렬 가능)
    cursor.execute("""
        SELECT user_name, COUNT(*) as cnt 
        FROM winners 
        GROUP BY user_id 
        ORDER BY cnt DESC, MIN(solved_at) ASC 
        LIMIT 10
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "🏆 아직 기록된 정답자가 없습니다."

    ranking_lines = ["🏆 [추리게임 정답 순위 TOP 10]"]
    for idx, (user_name, count) in enumerate(rows, start=1):
        ranking_lines.append(f"{idx위. {user_name} ({count}회)")
    
    return " / ".join(ranking_lines)

# -------------------------------------------------------------------------
# 웹소켓 URL 동적 획득 함수
# -------------------------------------------------------------------------
async def get_live_websocket_url(broadcast_id: str, token: str) -> str:
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json"
    }
    
    clean_id = broadcast_id.split("/")[-1].replace("@", "")
    api_url = f"https://kr-api.spooncast.net/lives/{clean_id}/"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(api_url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="방송 정보를 가져오지 못했습니다. ID나 토큰을 확인하세요.")
        
        data = response.json()
        try:
            ws_url = data.get("results", {}).get("web_url") or f"wss://kr-live.spooncast.net/api/v2/lives/{clean_id}/sockets/"
            return ws_url
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"웹소켓 주소 파싱 오류: {str(e)}")

# -------------------------------------------------------------------------
# AI 추리 답변 생성 함수
# -------------------------------------------------------------------------
async def get_ai_answer(prompt: str) -> str:
    try:
        if not config_data["openai_api_key"]:
            return "AI API 키가 설정되지 않아 답변할 수 없습니다."
        
        client = openai.OpenAI(api_key=config_data["openai_api_key"])
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 추리게임 진행 및 설정 안내자야. 플레이어의 질문에 대해 사건 설정에 맞게 이성적이고 흥미롭게 짧게 답변해줘."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 응답 생성 중 오류가 발생했습니다: {str(e)}"

# -------------------------------------------------------------------------
# 봇 메인 루프 (채팅 수신 및 명령어 처리)
# -------------------------------------------------------------------------
async def run_bot():
    global config_data
    while True:
        try:
            if not config_data["broadcast_id"] or not config_data["token"]:
                await asyncio.sleep(2)
                continue

            ws_url = await get_live_websocket_url(config_data["broadcast_id"], config_data["token"])
            headers = {
                "Authorization": f"Token {config_data['token']}"
            }

            print(f"[Bot] 웹소켓 연결 시도: {ws_url}")
            async with websockets.connect(ws_url, extra_headers=headers) as websocket:
                print("[Bot] 웹소켓 연결 성공!")
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    event = data.get("type")
                    if event in ["chat", "live_message"]:
                        content = data.get("message", "")
                        user_info = data.get("author", {})
                        user_name = user_info.get("nickname", "알 수 없음")
                        user_id = user_info.get("tag", "unknown")

                        print(f"[Chat] {user_name}: {content}")

                        # 1. '!정답' 명령어 처리 (데이터베이스 저장)
                        if content.startswith("!정답"):
                            save_winner(user_name, user_id)
                            print(f"[Game] 정답자 기록됨: {user_name} ({user_id})")

                        # 2. '!순위' 명령어 처리 (정답 횟수 순위 조회)
                        elif content.startswith("!순위"):
                            ranking_msg = get_ranking_text()
                            print(f"[Game 순위 조회 출력]: {ranking_msg}")
                            # TODO: ranking_msg를 스푼 채팅창으로 전송하는 API 호출 코드를 여기에 추가할 수 있습니다.

                        # 3. '!'로 시작하는 추리 질문 처리 (AI 연동)
                        elif content.startswith("!") and not content.startswith("!정답") and not content.startswith("!순위"):
                            question = content[1:]
                            ai_reply = await get_ai_answer(question)
                            print(f"[AI 답변 생성]: {ai_reply}")
                            # TODO: 생성된 ai_reply를 스푼 채팅창으로 전송하는 API 호출 코드를 여기에 추가할 수 있습니다.
                    
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[Bot] 웹소켓 연결 끊김 ({e}), 5초 후 재연결 시도...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Bot] 오류 발생: {e}, 5초 후 재연결 시도...")
            await asyncio.sleep(5)

# -------------------------------------------------------------------------
# FastAPI 엔드포인트
# -------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/config")
async def update_config(config: ConfigModel):
    global config_data, bot_task
    config_data["broadcast_id"] = config.broadcast_id
    config_data["token"] = config.token
    config_data["openai_api_key"] = config.openai_api_key

    try:
        await get_live_websocket_url(config.broadcast_id, config.token)
    except HTTPException as he:
        raise he

    if bot_task and not bot_task.done():
        bot_task.cancel()
    
    bot_task = asyncio.create_task(run_bot())
    
    return {"status": "success", "message": "설정이 업데이트되고 추리게임 봇이 실행되었습니다."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
