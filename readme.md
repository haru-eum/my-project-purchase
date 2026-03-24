# 📊 글로벌 원자재 가격 추적 대시보드 — MVP

전략구매 직무를 위한 원자재 가격 변동 리스크 모니터링 시스템

---

## 🗂️ 파일 구성

```
.
├── init_db.py              # DB 초기화 + 시드 데이터
├── backend/                # FastAPI API 서버
├── frontend/               # Next.js 프론트엔드
├── update_market_data.py   # FRED / EIA / BOK / yfinance 등 API 업서트
├── crawl_market_data.py    # Investing / USGS / Asian Metal 등 크롤·스크랩 업서트
├── scrapers/               # 사이트별 수집 모듈
├── db_io.py                # SQLite 업서트 공통
├── requirments.txt         # 의존 패키지
└── scm_dashboard.db        # SQLite DB
```

---

## 🚀 실행 방법 (추천 흐름)

### 1단계: 패키지 설치
```bash
pip install -r requirments.txt
```
```bash
cd frontend && npm install
```

### 2단계: DB 초기화 (최초 1회만)
```bash
python init_db.py
```
→ `scm_dashboard.db` 생성. **원자재 13종(열연강판·갈륨·인듐 포함)** 시드가 들어갑니다.

### (선택) API·크롤 데이터 반영
```bash
# .env 에 FRED / EIA / BOK 키 설정 후
python update_market_data.py

# Selenium 등 설치 후 — 사이트 구조·약관 준수는 사용자 책임
python crawl_market_data.py
```

### 3단계: 원클릭 실행 (권장)
```bash
python run_all.py
```
→ 프론트: `http://localhost:3000` / API: `http://localhost:8000`

### 4단계: 종료
```bash
python stop_all.py
```

### (참고) 수동 실행
```bash
# 터미널 1
cd backend
python main.py

# 터미널 2
cd frontend
npm run dev
```

---

## 🏗️ 아키텍처 설명

### DB 테이블 구조

```sql
RawMaterials          -- 원자재 마스터 (구리, 알루미늄, 니켈, ...)
PriceHistory          -- 일별 달러 시세 (USD/MT, USD/BBL ...)
ExchangeRates         -- 일별 USD/KRW 환율

-- 핵심 계산식 (세 테이블 JOIN)
수입원가(KRW) = price_usd × usd_krw
```

### 핵심 SQL 쿼리 구조

```sql
SELECT
    ph.price_date,
    rm.name_kr,
    ph.price_usd,
    er.usd_krw,
    ROUND(ph.price_usd * er.usd_krw, 0) AS 수입원가_KRW  ← 핵심
FROM PriceHistory ph
INNER JOIN RawMaterials  rm ON rm.material_id = ph.material_id
INNER JOIN ExchangeRates er ON er.rate_date   = ph.price_date
WHERE ph.price_date BETWEEN ? AND ?
```

### 가상 데이터 생성 방법
- **가격 시계열**: 기하 브라운 운동(GBM) 모델 적용
- **환율**: USD/KRW 1,300원 기준, 연 변동성 8% GBM
- **데이터 기간**: 2024-01-01 ~ 2025-03-31 영업일 기준 약 330일

---

## 📊 대시보드 기능

| 탭 | 기능 |
|---|---|
| 📈 가격 추이 | 원자재별 수입원가(KRW) / 달러가격 라인차트 + 21일 이동평균 + 환율 추이 |
| 📉 변동률 분석 | 전일/전주/전월 대비 변동률 그룹바차트 + 상세 테이블 |
| 🗓️ 히트맵 | 원자재 × 월별 수입원가 히트맵 |
| 🎯 리스크 레이더 | 연환산 변동성 기반 리스크 레이더차트 + 등급 순위 |

### 리스크 등급 기준
- 🔴 **HIGH**: 연환산 변동성 ≥ 30% → 헤징 전략 필수 검토
- 🟡 **MEDIUM**: 연환산 변동성 ≥ 15% → 장기계약·선도환 고려
- 🟢 **LOW**: 연환산 변동성 < 15% → 현물 구매 유지 가능

---

## 🔧 향후 확장 방향 (Phase 2)

- [ ] **실시간 API 연동**: LME(런던금속거래소), EIA(에너지정보청), 한국은행 환율 API
- [ ] **알림 기능**: 변동률 임계치 초과 시 이메일/슬랙 알림
- [ ] **예측 모델**: ARIMA / Prophet 기반 가격 예측
- [ ] **구매 의사결정 지원**: 적정 구매 시점 시그널 생성
- [ ] **ERP 연동**: SAP MM 모듈 연계

---

## 📦 원자재 목록 (가상 데이터)

| 원자재 | 단위 | 기준가(USD) | 연환산변동성 |
|--------|------|-------------|-------------|
| 구리   | MT   | 8,500       | ~18%        |
| 알루미늄 | MT | 2,400       | ~15%        |
| 니켈   | MT   | 17,000      | ~28%        |
| 열연강판 | MT | 650         | ~12%        |
| 원유   | BBL  | 80          | ~25%        |
| LNG    | MMBTU| 3           | ~40%        |
| 폴리에틸렌 | MT | 1,200     | ~14%        |
| 리튬   | MT   | 15,000      | ~50%        |