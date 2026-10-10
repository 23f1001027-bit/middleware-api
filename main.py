import math
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

EMAIL = "23f1001027@ds.study.iitm.ac.in"
ALLOWED_ORIGINS = [
    "https://app-k8muel.example.com",   # assigned origin
    "https://exam.sanand.workers.dev",  # exam page origin: confirm in your address bar
]
BUCKET = 10
WINDOW = 10.0


class RateLimiter:
    """Sliding-window log, one bucket per client id."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, client_id: str):
        now = time.monotonic()
        with self.lock:
            q = self.hits[client_id]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, math.ceil(q[0] + self.window - now))
            q.append(now)
            return True, 0


limiter = RateLimiter(BUCKET, WINDOW)

app = FastAPI()


# registered first = innermost
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client_id = request.headers.get("x-client-id")
    if client_id and request.method != "OPTIONS":
        allowed, retry_after = limiter.check(client_id)
        if not allowed:
            return JSONResponse(
                {"error": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


# registered last = outermost, so every response (incl. 429) gets CORS headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
    allow_credentials=False,
)


@app.get("/ping")
def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}


@app.get("/")
def root():
    return {"status": "ok"}
