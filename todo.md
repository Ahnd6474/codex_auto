# TODO

## 0) 우선순위/로드맵

### P0 (핵심 사용자 경험)
1. **모드 분리: 개발자 모드 / 일반인 모드**
2. **추론 설정 `auto` 도입 + 모델 `gpt-5.4` 고정**
3. **개발자 모드 UI 간편화**
4. **오프라인/중단 복구(재시작 가능) 구조**
5. **직렬 처리 → 단계별 병렬 처리 파이프라인**

### P1 (확장 가치)
6. **다국어(한국어/영어) 지원**
7. **산출물 옵션: 웹사이트/보고서/PPT 자동 생성**
8. **원격 진행상황 공유 링크 기능**

### P2 (전략 과제)
9. **ML(머신러닝) 모드 추가**
10. **Windows 기반 앱 출시 강화**
11. **Codex 검색 항상 허용 정책 정리**
12. **문제 발생 시 PR 로그/리포트 자동 보고**
13. **Git 충돌 발생 시 코드 선택 정책/절차**
14. **예상 실행 시간(레벨별/실행중 동적) 표시**
15. **OpenCDK 연동 API 지원 추가**
16. **API 비용(토큰 사용/CLI API 사용 시) 예상 금액 표시**

---

## 1) 모드 분리: 개발자 모드 / 일반인 모드

### 목표
- 사용자 진입점을 명확히 나눠서 복잡도를 낮춘다.

### 요구사항
- **개발자 모드**: 기존 기능 유지 + UI를 더 간결하게 제공.
- **일반인 모드**: ChatGPT처럼 “알아서 진행” 중심 UX 제공.
- 일반인 모드 기본값:
  - 추론 설정: `auto`
  - 결과 보고: 자동 생성(최소 보고서)

### 스켈레톤(예시 함수/모듈)
- `get_user_mode() -> Literal["developer", "general"]`
- `build_mode_profile(mode) -> ModeProfile`
- `apply_mode_defaults(config, mode_profile) -> RuntimeConfig`

### 완료 기준
- 모드 전환 UI/CLI에서 1회 선택으로 동작.
- 모드별 기본값이 런타임에 일관되게 반영.

---

## 2) 추론 설정 `auto` 도입 (기존 low/medium/high/xhigh 유지), 모델 gpt-5.4 고정

### 목표
- 작업 난이도에 따라 자동으로 추론 강도를 선택하되, 수동 설정도 유지.

### 요구사항
- 지원 값: `auto | low | medium | high | xhigh`
- `auto` 동작:
  - 작업 분석 후 `medium/high/xhigh` 중 선택
  - 단순 작업은 `medium`, 복합 작업은 `high`, 고위험/대규모는 `xhigh`
- 모델은 **항상 `gpt-5.4` 고정**

### 스켈레톤(예시 함수/모듈)
- `class ReasoningLevel(Enum): AUTO, LOW, MEDIUM, HIGH, XHIGH`
- `estimate_task_complexity(task_ctx) -> ComplexityScore`
- `resolve_reasoning_level(requested_level, task_ctx) -> ReasoningLevel`
- `resolve_model_name() -> str  # always "gpt-5.4"`

### 테스트 아이디어
- `auto` 입력 시 난이도별 매핑 검증.
- 수동 `low~xhigh` 지정 시 기존 동작 회귀 테스트.
- 모델 강제 고정 테스트(`gpt-5.4` 외 값 거부/무시).

---

## 3) 개발자 모드 UI 간편화

### 문제
- 텍스트/정보량 과다, 자유도 과다, 버튼 과다.

### 개선 방향
- 기본 화면을 “자주 쓰는 흐름” 중심으로 축소.
- 고급 옵션은 접기(advanced panel)로 이동.
- 주요 CTA를 2~3개로 제한.
- 상태/로그는 요약 + 상세 펼침 구조로 변경.

### 스켈레톤(예시 함수/컴포넌트)
- `build_developer_quick_actions()`
- `render_advanced_controls(collapsed=True)`
- `summarize_runtime_status(state) -> StatusSummary`

### 완료 기준
- 초기 화면 버튼 수/텍스트량 감소.
- 기존 핵심 기능 접근성 유지.

---

## 4) 다국어 기능 (한국어/영어)

### 목표
- UI/메시지/보고서 템플릿에 i18n 적용.

### 요구사항
- 지원 언어: `ko`, `en`
- 사용자 설정 + 시스템 기본 언어 fallback
- 번역 키 누락 시 안전 fallback(영어 또는 한국어 기본)

### 스켈레톤(예시 함수/모듈)
- `translate(key, locale, **kwargs) -> str`
- `detect_default_locale() -> str`
- `load_locale_bundle(locale) -> dict[str, str]`

### 완료 기준
- 주요 사용자 플로우에서 한/영 전환 즉시 반영.

---

## 5) 장애 대비 재시작/복구 (네트워크 끊김, 전원 종료, 서버 장애)

### 목표
- 작업 중단 후에도 안전하게 재개 가능.

### 요구사항
- 단계별 체크포인트 저장(입력/중간결과/진행률).
- 재시작 시 마지막 안전 지점에서 resume.
- 실패 원인/재시도 정책(백오프, 최대 횟수) 기록.

### 스켈레톤(예시 함수/모듈)
- `save_checkpoint(run_id, stage, payload)`
- `load_latest_checkpoint(run_id)`
- `resume_run(run_id)`
- `should_retry(error, attempt) -> bool`

### 테스트 아이디어
- 강제 중단 후 재시작 시 이어서 진행되는지 검증.
- 네트워크 오류 시 재시도/중단 정책 검증.

---

## 6) 종료 후 산출물 옵션 (웹사이트/보고서/PPT)

### 목표
- 작업 종료 시 후처리 산출물을 선택적으로 생성.

### 요구사항
- 옵션: `website`, `report`, `ppt`
- **일반인 모드**: `report` 자동 생성(기본 ON)
- **개발자 모드**: 사용자 선택형(기본 OFF 또는 마지막 선택 기억)

### 스켈레톤(예시 함수/모듈)
- `get_postprocess_options(mode) -> PostProcessOptions`
- `generate_report(context)`
- `generate_website(context)`
- `generate_ppt(context)`

### 완료 기준
- 모드별 기본 동작 차이가 명확히 반영.

---

## 7) 처리 파이프라인 고도화 (직렬 → 단계 기반 병렬)

### 목표
- 현재 단일 직렬 처리에서, 단계별 병렬화를 통해 생산성 향상.

### 제안 파이프라인
1. **스켈레톤 코드 작성/함수 명명 + 테스트 제작** (`auto` 기대: `xhigh`)
2. **병렬 처리 실행** (`auto` 기대: `medium~xhigh`)
3. **마무리 및 최종 점검** (`auto` 기대: `xhigh`)

### 스켈레톤(예시 함수/모듈)
- `plan_pipeline(task) -> PipelinePlan`
- `run_parallel_stage(stage_plan)`
- `collect_parallel_results(stage_id)`
- `final_validation(run_artifacts)`

### 테스트 아이디어
- 병렬 단계 결과 병합 충돌 처리 검증.
- 최종 점검 단계에서 품질 게이트 실패 처리 검증.

---

## 8) 원격 진행 상황 공유 링크 생성

### 목표
- 로컬 작업 상태를 원격 웹 링크로 조회 가능하게 제공.

### 요구사항
- 실행별 고유 링크 발급/만료 정책.
- 읽기 전용 상태 대시보드.
- 민감정보 마스킹/접근 제어.

### 스켈레톤(예시 함수/모듈)
- `create_share_link(run_id, ttl) -> str`
- `publish_progress_snapshot(run_id, snapshot)`
- `revoke_share_link(link_id)`

### 완료 기준
- 외부에서 진행률/상태/최근 로그 요약 확인 가능.

---

## 9) ML(머신러닝) 모드 추가

### 목표
- ML 작업 특화 템플릿/파이프라인 제공.

### 요구사항
- 데이터 준비/학습/평가/리포트 단계를 기본 제공.
- 실험 메타데이터 및 결과 비교 저장.

### 스켈레톤(예시 함수/모듈)
- `run_ml_mode(task_config)`
- `track_experiment(exp_config, metrics)`
- `compare_experiments(exp_ids)`

---

## 10) Windows 기반 앱 출시

### 목표
- Windows 사용자 대상 배포 품질 강화.

### 요구사항
- 설치/업데이트/권한 이슈 점검.
- Windows UX 가이드에 맞는 기본값/단축키/경로 처리.
- 배포 아티팩트/서명/릴리스 노트 체계화.

### 스켈레톤(예시 함수/모듈)
- `build_windows_release()`
- `validate_windows_runtime()`
- `package_desktop_artifacts(platform="windows")`

---

## 11) Codex 검색 항상 허용

### 목표
- 작업 수행 시 검색 기능을 기본 허용으로 운영.

### 요구사항
- 기본값: 검색 ON
- 보안/규정상 제한 시 명시적 경고 + 대체 플로우 제공
- 로그에 “검색 사용 여부/출처” 기록

### 스켈레톤(예시 함수/모듈)
- `is_search_enabled(config) -> bool`
- `enforce_search_policy(config, runtime_env)`
- `log_search_usage(run_id, query_meta)`

---

## 12) 문제 발생 시 PR에 로그/리포트 보고

### 목표
- 실행 중 오류가 발생하면 관련 로그/원인/재현정보를 PR에 자동 첨부해 추적성을 높인다.

### 요구사항
- 실패 시점의 핵심 로그(요약 + 상세 링크/첨부) 자동 수집
- PR 코멘트 또는 PR 본문 업데이트로 상태 보고
- 민감정보 마스킹 후 업로드

### 스켈레톤(예시 함수/모듈)
- `collect_failure_bundle(run_id) -> FailureBundle`
- `format_pr_failure_report(bundle) -> str`
- `post_pr_status_update(pr_id, report_markdown)`

### 완료 기준
- 주요 실패 케이스에서 PR에 자동 보고가 남고, 재현에 필요한 정보가 누락되지 않음.

---

## 13) Git 충돌 발생 시 코드 선택 정책/절차

### 목표
- 충돌 해결 시 일관된 기준으로 어느 코드를 채택할지 결정한다.

### 요구사항
- 충돌 유형 분류(기능 변경 충돌/포맷 충돌/삭제-수정 충돌)
- 선택 우선순위 정책 명시
  - 안정성/테스트 통과 코드 우선
  - 최신 요구사항(스펙) 우선
  - 로그/상태 추적성 보존 우선
- 자동 해결 불가 시 인간 승인 포인트 제공

### 스켈레톤(예시 함수/모듈)
- `class ConflictResolutionPolicy(Enum)`
- `analyze_conflict(hunk) -> ConflictType`
- `select_conflict_side(conflict_ctx, policy) -> ResolutionDecision`
- `apply_resolution_with_audit(decision)`

### 완료 기준
- 충돌 해결 결과에 대해 "왜 이 코드를 선택했는지" 감사 로그가 남음.

---

## 14) 예상 실행 시간 추가 (레벨별 사전 + 실행중 동적 갱신)

### 목표
- 시작 전/실행 중 모두 예상 소요 시간을 제공해 사용자 예측 가능성을 높인다.

### 요구사항
- 초기 추정: `low/medium/high/xhigh` 레벨별 기준 시간 테이블 제공
- 실행 중 추정: 현재 처리 블록 수 + 추론 레벨 + 과거 평균 처리속도로 ETA 갱신
- 표시 항목: 시작 추정치, 현재 ETA, 신뢰도(낮음/보통/높음)

### 스켈레톤(예시 함수/모듈)
- `estimate_initial_duration(reasoning_level, task_type) -> DurationEstimate`
- `update_runtime_eta(progress_blocks, reasoning_level, throughput) -> DurationEstimate`
- `render_eta_badge(estimate)`

### 테스트 아이디어
- 레벨별 초기 추정치 로딩/표시 검증
- 진행률 변화에 따른 ETA 단조 감소/재계산 검증
- 장기 작업에서 ETA 튐(스파이크) 완화 로직 검증

---

## 15) OpenCDK 연동 API 지원 추가

### 목표
- OpenCDK 기반 워크플로우와 codex-auto를 연동해 외부 시스템에서도 자동화 실행/조회 API를 사용할 수 있게 한다.

### 요구사항
- 인증 방식(API Key/OAuth 등)과 권한 스코프 정의
- 실행 트리거 API(작업 시작/중지/재시작) 제공
- 상태 조회 API(진행률/최근 로그/실패 원인 요약) 제공
- 버전 호환성 정책(최소 지원 OpenCDK 버전) 문서화

### 스켈레톤(예시 함수/모듈)
- `register_opencdk_provider(config) -> OpenCDKProvider`
- `start_run_via_opencdk(request) -> RunHandle`
- `get_run_status_via_opencdk(run_id) -> OpenCDKRunStatus`
- `map_opencdk_error(error) -> RetryableError | FatalError`

### 완료 기준
- OpenCDK 연동 환경에서 최소 1개 샘플 파이프라인이 시작→완료까지 정상 동작.

---

## 16) API 금액 예상치 표시 (API 직접 사용 / Codex CLI API 사용)

### 목표
- 실행 전에 예상 비용을 보여주고, 실행 중/종료 후 실제 비용 추정치를 제공해 운영비 예측 가능성을 높인다.

### 요구사항
- 입력 토큰/출력 토큰/캐시 토큰(해당 시) 기준 비용 계산
- 모드(개발자/일반인), 추론 레벨, 모델 고정값(`gpt-5.4`) 반영
- 비교 표시:
  - API 직접 호출 예상 금액
  - Codex CLI API 경유 예상 금액
- 실행 중 누적 비용 및 종료 후 최종 비용 리포트 표시
- 요금표 업데이트 시점/버전 기록(계산 근거 추적성 확보)

### 스켈레톤(예시 함수/모듈)
- `load_pricing_table(source, effective_date) -> PricingTable`
- `estimate_run_cost(usage_plan, pricing_table) -> CostEstimate`
- `compare_api_vs_cli_cost(task_ctx, usage_forecast) -> CostComparison`
- `accumulate_runtime_cost(usage_events, pricing_table) -> CostSummary`
- `render_cost_breakdown(summary, locale) -> str`

### 테스트 아이디어
- 고정된 토큰 사용량 입력에 대해 비용 계산 회귀 테스트
- 요금표 버전 변경 시 예상 금액 재계산 테스트
- API 직접 사용 vs CLI API 비교 출력 정확도 테스트

---

## 제안 일정 (초안)
- **1주차**: 1, 2, 3번 설계/프로토타입
- **2주차**: 4, 5번(국제화/복구) 핵심 구현
- **3주차**: 6, 7, 14번(산출물/병렬/ETA)
- **4주차**: 8, 9, 10, 11, 12, 13번 및 통합 테스트
- **5주차**: 15, 16번(OpenCDK 연동/API 비용 추정) 및 운영 문서화

## 메모
- `auto`는 설명 가능성(왜 medium/high/xhigh가 선택됐는지)을 함께 기록하면 운영/디버깅에 유리.
- 일반인 모드는 설정 자유도를 줄이고, 실패 시 자동 복구 흐름을 우선 제공.
