# 웹 배포 가이드 (Docker 없이)

## 목표 구조

- 프론트: `frontend/` → **Vercel**
- 백엔드: `backend/` → **Render 또는 Railway**
- DB: 루트의 `scm_dashboard.db` (영구 디스크에 보관)

---

## 1) 백엔드 배포 (Render 기준)

### 새 Web Service 생성

- Repository: 현재 저장소 연결
- Root Directory: `backend`
- Runtime: Python
- Build Command:

```bash
pip install -r requirements.txt
```

- Start Command:

```bash
python main.py
```

### 환경 변수

- `UVICORN_RELOAD=0`
- `DB_PATH=/opt/render/project/src/scm_dashboard.db`
- `CORS_ORIGINS=https://<your-vercel-domain>`
- `CORS_ORIGIN_REGEX=https://.*\.vercel\.app`

### DB 파일 준비

SQLite는 파일 기반이라 서버 디스크에 파일이 있어야 합니다.

1. 로컬에서 초기화:

```bash
python init_db.py
```

2. 생성된 `scm_dashboard.db`를 Render Persistent Disk 경로로 올리거나(SSH/Shell), 배포 후 서버 셸에서 `python ../init_db.py`를 1회 실행하세요.

---

## 2) 프론트 배포 (Vercel)

### 프로젝트 생성

- Import Git Repository
- Root Directory: `frontend`
- Framework: Next.js (자동 감지)

### 환경 변수

- `NEXT_PUBLIC_API_URL=https://<your-backend-domain>`

배포 후 `https://<your-vercel-domain>` 접속.

---

## 3) 동작 점검

- API 헬스: `https://<backend-domain>/docs`
- 프론트: `https://<vercel-domain>`
- 브라우저 개발자도구에서 `/api/...` 호출이 백엔드 도메인으로 가는지 확인

---

## 4) 왜 이렇게 구성하나?

Vercel은 프론트 배포가 매우 쉽지만, SQLite 영속 저장과 장기 실행 프로세스에는 적합하지 않습니다.  
그래서 프론트는 Vercel, 백엔드(SQLite 포함)는 Render/Railway 같은 상시 서버로 분리하는 방식이 가장 안정적입니다.
