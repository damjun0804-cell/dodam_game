import asyncio
import json
import httpx
import websockets
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()

# 봇 상태 관리용 전역 변수
config_data = {
    "broadcast_id": "",
    "token": ""
}
bot_task = None

class ConfigModel(BaseModel):
    broadcast_id: str
    token: str

@app.get("/", response_class=HTMLResponse)
async def read_root():
    # 위 HTML 내용을 반환하거나 템플릿을 연결합니다.
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

async def get_live_websocket_url(broadcast_id: str, token: str) -> str:
    """스푼라디오 API를 통해 방송 ID로부터 최신 웹소켓 접속 URL을 동적으로 가져옵니다."""
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json"
    }
    
    # 1. 만약 입력값이 URL 형태이거나 고유닉 형태라면 ID를 파싱하거나 조회하는 로직을 수행할 수 있습니다.
    # 예: 방송 ID가 숫자가 아니거나 고유닉(@포함 등)인 경우 대응 처리 가능
    clean_id = broadcast_id.split("/")[-1].replace("@", "")

    # 스푼라디오 라이브 상세 정보 API 호출 (예시 엔드포인트 구조)
    api_url = f"https://kr-api.spooncast.net/lives/{clean_id}/"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(api_url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="방송 정보를 가져오지 못했습니다. ID나 토큰을 확인하세요.")
        
        data = response.json()
        try:
            # 응답 구조에서 웹소켓 주소 추출 (공식 규격에 맞춤)
            # 만약 API가 웹소켓 URL을 직접 주지 않고 라이브 데이터만 준다면 아래와 같이 직접 조합합니다.
            ws_url = data.get("results", {}).get("web_url") or f"wss://kr-live.spooncast.net/api/v2/lives/{clean_id}/sockets/"
            return ws_url
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"웹소켓 주소 파싱 오류: {str(e)}")

async def run_bot():
    """웹소켓에 백그라운드로 접속하여 채팅을 수신하고 처리하는 메인 루프"""
    global config_data
    while True:
        try:
            if not config_data["broadcast_id"] or not config_data["token"]:
                await asyncio.sleep(2)
                continue

            # 동적으로 웹소켓 주소 획득
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
                    
                    # 수신된 채팅 데이터 처리 로직 구현
                    print(f"[Chat Received]: {data}")
                    
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[Bot] 웹소켓 연결 끊김 ({e}), 5초 후 재연결 시도...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Bot] 오류 발생: {e}, 5초 후 재시도...")
            await asyncio.sleep(5)

@app.post("/api/config")
async def update_config(config: ConfigModel):
    global config_data, bot_task
    config_data["broadcast_id"] = config.broadcast_id
    config_data["token"] = config.token

    # 유효성 검증을 겸하여 웹소켓 주소 정상 취득 여부 확인
    try:
        await get_live_websocket_url(config.broadcast_id, config.token)
    except HTTPException as he:
        raise he

    # 이미 실행 중인 봇 태스크가 있다면 취소 후 재시작
    if bot_task and not bot_task.done():
        bot_task.cancel()
    
    bot_task = asyncio.create_task(run_bot())
    
    return {"status": "success", "message": "설정이 업데이트되고 봇이 실행되었습니다."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
