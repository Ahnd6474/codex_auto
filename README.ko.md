# jakal-flow (한국어)

`jakal-flow`는 여러 저장소를 격리된 워크스페이스로 운영하면서, 저장소별 계획, 체크포인트, 로그, 메모리, 리포트, 롤백 상태, 공유 세션, 아카이브 히스토리를 분리해 유지하는 Python 중심 자동화 도구입니다. 핵심 경로는 Python 오케스트레이션 코어에 있고, 데스크톱 UI와 공유 뷰어는 그 위에 올라가는 보조 표면입니다.

영문 문서는 [README.md](README.md)를 참고하세요.

## 아키텍처

전체 표면과 워크스페이스 격리 구조:

![jakal-flow 흐름도 (KO)](assets/readme-flow-ko.svg)

백엔드 계획 생성, 실행, 검증, 롤백, 리포트 흐름:

![jakal-flow 백엔드 코드 생성 흐름 (KO)](assets/backend-codegen-flow-ko.svg)

## 빠른 시작

권장 런타임:

- Python 3.11+
- `PATH`에 있는 Codex CLI
- 데스크톱 셸용 Node.js 20+, Rust, Tauri 선행조건

패키지 설치:

```bash
python -m pip install -e .
```

설치 후 사용할 수 있는 엔트리포인트:

- `jakal-flow`
- `jakal-flow-ui-bridge`

설치 스크립트와 모듈 엔트리포인트는 서로 대응합니다.

- `jakal-flow` == `python -m jakal_flow`
- `jakal-flow-ui-bridge` == `python -m jakal_flow.ui_bridge`

체크아웃 기준 실제 명령 표면 확인:

```bash
jakal-flow --help
jakal-flow run --help
```

관리 저장소 초기화:

```bash
jakal-flow init-repo \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --plan-prompt "완성도 높은 결과물과 강한 검증, 마감 정리를 목표로 안전한 프로젝트 계획을 만들어라." \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest"
```

검증 포함 개선 루프 실행:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 2
```

같은 관리 저장소를 나중에 다시 이어서 실행:

```bash
jakal-flow resume \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 2
```

상태 확인:

```bash
jakal-flow list-repos --workspace-root .jakal-flow-workspace
jakal-flow status --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
jakal-flow history --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --limit 20
jakal-flow report --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
```

`list-repos`는 JSON 요약을 출력하고, `report`는 최신 기계 판독용 리포트 파일 경로를 출력합니다.

기본 출력 형식:

| 명령 | 출력 |
| --- | --- |
| `list-repos` | 저장소 식별자, 상태, safe revision, 마지막 실행 시각이 들어 있는 JSON 배열 |
| `status` | `metadata`와 `loop_state`를 담은 JSON 객체 |
| `history` | 블록별 사람이 읽기 쉬운 요약 줄 |
| `report` | `reports/latest_report.json` 파일 경로 |

데스크톱 개발 실행:

```bash
cd desktop
npm install
npm run test
npm run tauri:dev
```

## 왜 jakal-flow인가

- 다중 저장소 전제: 관리 저장소마다 독립된 프로젝트 트리를 가집니다.
- 추적성 우선: 계획, 체크포인트, UI 이벤트, 검증 실행, 블록 로그, 리포트, SVG, 태스크 메모리를 남깁니다.
- 안전한 실행: safe revision, 롤백, 체크포인트 승인, 검증된 커밋만 반영하는 흐름을 유지합니다.
- 하나의 백엔드, 여러 표면: CLI, 데스크톱 셸, 임시 공유 모니터가 모두 같은 Python 코어를 사용합니다.
- 유연한 모델 라우팅: OpenAI/Codex, Claude Code, Gemini CLI, Qwen Code, OpenAI 호환 공급자, Anthropic 호환 공급자, 로컬 OSS 백엔드를 연결할 수 있습니다.
- 장기 보존용 히스토리: 데스크톱 셸에서 완료된 관리 워크스페이스를 `history/`로 아카이브할 수 있습니다.

## 현재 지원 범위

### 표면

| 표면 | 지원 내용 |
| --- | --- |
| CLI | `init-repo`, `run`, `resume`, `list-repos`, `status`, `history`, `report` |
| 데스크톱 UI | 기존 로컬 저장소 등록, 런타임 기본값 저장, 계획 생성/편집, 실행/중단 제어, 체크포인트 승인, 히스토리 아카이브/삭제, 공유 세션 관리 |
| 원격 모니터 | 로컬 공유 서버, 임시 공유 세션, 마스킹된 상태/로그, 실행 흐름 SVG, 선택적 공개 URL, 선택적 Cloudflare Quick Tunnel, 원격 pause, 남은 작업이 있을 때 원격 resume |

### 워크플로

| 기능 | 지원 여부 |
| --- | --- |
| 일반 소프트웨어 워크플로 | 예 |
| ML 실험 워크플로 | 예, `--workflow-mode ml` |
| 자동 ML 재계획 | 예, 최대 `--ml-max-cycles` |
| 계획 생성 방식 | Planner Agent A 분해 + Planner Agent B 패킹 |
| 실행 방식 | 병렬 DAG 스케줄링이 기본 정규화 모드 |
| Hybrid lineage / join / barrier step | 예 |
| Closeout 패스 | 예, 일반 step과 별도 |
| 현재 step 이후 일시정지 | 예, 데스크톱과 공유 모니터에서 가능 |
| 즉시 중단 | 예, 데스크톱에서 가능 |

### 모델 / 공급자

| 공급자 프리셋 | 지원 여부 | 비고 |
| --- | --- | --- |
| `openai` | 예 | OpenAI / Codex 클라우드 |
| `ensemble` | 예 | 기본 계획/일반 작업은 OpenAI를 쓰고, step 단위로 UI 또는 명시적 작업을 다른 백엔드로 라우팅 가능 |
| `claude` | 예 | Claude Code print-mode |
| `gemini` | 예 | Gemini CLI headless |
| `qwen_code` | 예 | Qwen Code headless |
| `deepseek` | 예 | DeepSeek Anthropic 호환 엔드포인트를 Claude Code로 사용 |
| `kimi` | 예 | Moonshot Kimi OpenAI 호환 경로 |
| `minimax` | 예 | MiniMax Anthropic 호환 엔드포인트를 Claude Code로 사용 |
| `glm` | 예 | GLM Anthropic 호환 엔드포인트를 Claude Code로 사용 |
| `openrouter` | 예 | OpenAI 호환 엔드포인트 |
| `opencdk` | 예 | OpenAI 호환 엔드포인트 |
| `local_openai` | 예 | LM Studio, vLLM, llama.cpp, LocalAI 같은 로컬 OpenAI 호환 서버 |
| `oss` | 예 | 로컬 제공자를 통한 Codex OSS 모드 |

`--model-provider oss`에서 쓸 수 있는 로컬 제공자:

- `ollama`
- `lmstudio`

추론 강도:

- `low`
- `medium`
- `high`
- `xhigh`

### 계획, 실행, 검토

| 기능 | 지원 여부 |
| --- | --- |
| 저장형 프로젝트 계획 생성 | 예 |
| Planner Agent A 개요 저장 | 예, `docs/PLAN_AGENT_A_OUTLINE.md` |
| Mid-term subset 재생성 | 예 |
| 의존성 기반 실행 트리 | 예 |
| step 단위 provider/model override | 예 |
| step 단위 reasoning effort | 예 |
| step 단위 success criteria | 예 |
| step 단위 verification command override | 예 |
| owned-path 기반 병렬 안전성 | 예 |
| 실행 전 step 수동 편집 | 예 |
| 데스크톱 백그라운드 폴링 | 예 |
| 체크포인트 타임라인과 승인 상태 | 예 |

### 안전성, 복구, 산출물

| 기능 | 지원 여부 |
| --- | --- |
| Safe revision 기록 | 예 |
| 회귀 시 롤백 | 예 |
| 검증된 커밋만 반영 | 예 |
| 안전 실행 후 선택적 push | 예, `--allow-push`와 `origin`이 있을 때 |
| Verification cache 재사용 | 예 |
| PR용 실패 번들 생성 | 예 |
| GitHub 토큰 기반 PR 실패 보고 | 예 |
| Closeout markdown 리포트 | 예 |
| Word closeout 리포트 | 예, `--word-report` 또는 데스크톱 토글 |
| Execution flow SVG | 예 |
| ML experiment 결과 SVG | 예 |
| 시간/비용 추정 | 예 |
| Codex 사용량 집계 | 예 |

## 데스크톱 UI

데스크톱 셸은 Python 백엔드를 유지한 채, 계획과 실행, 모니터링, 프로젝트 히스토리 관리를 위한 제어 계층을 제공합니다.

데스크톱 앱에서 할 수 있는 일:

- 기존 로컬 저장소를 관리 프로젝트로 등록
- provider, model, Codex 경로, 체크포인트 규칙, 병렬 워커 설정 같은 런타임 기본값 저장
- 실행 계획 생성, DAG 편집, 재계획 수행
- 의존성, owned path, hybrid lineage step, 최근 로그, 생성된 리포트 확인
- 실행 시작, 즉시 중단 요청, 현재 step 이후 pause, closeout 실행
- 남은 시간 추정, 비용 추정, 최근 실제 비용, Codex 사용량 창 확인
- 임시 원격 모니터 링크 생성/복사/철회
- 완료된 관리 워크스페이스를 히스토리로 아카이브하거나 오래된 히스토리 삭제
- 대시보드 카드, 테마, 언어, 백그라운드 동시성 제한 변경

데스크톱 빌드:

```bash
cd desktop
npm run tauri:build
```

관련 문서:

- [desktop/README.md](desktop/README.md)
- [website/README.md](website/README.md)

## 설정

`jakal-flow`는 CLI 런타임 옵션과 데스크톱 저장 기본값을 함께 지원합니다.

### CLI / 런타임 설정

| 그룹 | 지원 옵션 |
| --- | --- |
| 저장소 지정 | `--repo-url`, `--branch`, `--workspace-root`, `--plan-file`, `--resume` |
| 모델 선택 | `--model-provider`, `--local-model-provider`, `--model`, `--effort`, `--fast` |
| 공급자 연결 | `--provider-base-url`, `--provider-api-key-env` |
| 비용 추정 | `--billing-mode`, `--input-cost-per-million-usd`, `--cached-input-cost-per-million-usd`, `--output-cost-per-million-usd`, `--reasoning-output-cost-per-million-usd`, `--per-pass-cost-usd` |
| 워크플로 제어 | `--workflow-mode`, `--ml-max-cycles`, `--max-blocks`, `--extra-prompt`, `--plan-prompt` |
| 최적화 제어 | `--optimization-mode`, `--optimization-large-file-lines`, `--optimization-long-function-lines`, `--optimization-duplicate-block-lines`, `--optimization-max-files` |
| 안전성과 검증 | `--approval-mode`, `--sandbox-mode`, `--test-cmd`, `--allow-push` |
| 리포팅 | `--word-report` |

현재 checkout 기준 명령 표면 확인:

```bash
jakal-flow --help
jakal-flow run --help
```

### 데스크톱 저장 기본값

데스크톱 셸은 추가로 다음 값을 저장합니다.

- `planning_effort`
- `parallel_worker_mode`, `parallel_workers`, `parallel_memory_per_worker_gib`
- `background_queue_priority`
- `checkpoint_interval_blocks`
- `require_checkpoint_approval`
- `codex_path`
- `allow_push`
- `save_project_logs`
- 대시보드 가시성 설정
- UI 테마와 언어
- 공유 서버 bind host와 public base URL
- 백그라운드 작업 동시성 제한

### 비용 모드

지원되는 비용 추정 모드:

- `included`
- `token`
- `per_pass`

### 제공자 예시

Ensemble 라우팅:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider ensemble \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

OpenRouter:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider openrouter \
  --provider-base-url https://openrouter.ai/api/v1 \
  --provider-api-key-env OPENROUTER_API_KEY \
  --billing-mode token \
  --model openai/gpt-4.1-mini \
  --effort medium \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Gemini CLI:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider gemini \
  --model gemini-3-flash-preview \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Claude Code:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider claude \
  --model claude-sonnet-4-6 \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Qwen Code:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider qwen_code \
  --model qwen3-coder-plus \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

로컬 OSS + Ollama:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider oss \
  --local-model-provider ollama \
  --model qwen2.5-coder:0.5b \
  --effort medium \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

ML 워크플로:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --workflow-mode ml \
  --ml-max-cycles 3 \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 6
```

## 동작 방식

### 요약

```text
CLI / Desktop UI / Share monitor
            |
            v
      Python orchestration core
            |
            +-- planning.py
            +-- codex_runner.py
            +-- git_ops.py
            +-- workspace.py
            +-- memory.py
            +-- reporting.py
            |
            v
  projects/<repo_slug>/
    repo/ docs/ memory/ logs/ reports/ state/
```

### 초기화 단계

1. 워크스페이스 아래에 격리된 프로젝트 디렉터리를 만듭니다.
2. 원격 저장소는 `repo/`로 clone 또는 갱신하고, 데스크톱에서는 기존 로컬 저장소 경로를 그대로 등록할 수도 있습니다.
3. `README.md`, `AGENTS.md`, `repo/docs/**`를 스캔합니다.
4. 저장형 계획, scope guard, Planner Agent A 개요, 체크포인트 타임라인을 준비합니다.
5. 현재 safe revision과 프로젝트 메타데이터를 저장소 바깥에 기록합니다.

### 실행 블록마다

1. 저장된 계획, 런타임 설정, 태스크 메모리를 불러옵니다.
2. Mid-term subset과 ready step을 다시 계산합니다.
3. 의존성이 충족된 step을 병렬 DAG 스케줄러로 실행합니다.
4. 검증을 수행하고 fingerprint가 같으면 verification cache를 재사용합니다.
5. 검증된 안전한 변경만 커밋합니다.
6. 회귀나 위험한 병합 결과가 나오면 마지막 safe revision으로 롤백합니다.
7. 로그, 리포트, SVG, 메모리를 갱신합니다.
8. 계획된 작업이 끝나면 별도의 closeout 패스를 실행합니다.

## 워크스페이스 구조

관리 저장소마다 독립된 프로젝트 트리를 가집니다.

```text
workspace_root/
  projects/
    <repo_slug>/
      repo/
      docs/
      memory/
      logs/
      reports/
      state/
      metadata.json
      project_config.json
  history/
    <archived_run_slug>/
  registry.json
```

원격 저장소를 관리할 때는 `repo/` 아래에 clone합니다. 데스크톱에서 기존 로컬 저장소를 등록한 경우에는 원본 체크아웃을 그대로 두고, 관리 루트에는 `docs/`, `memory/`, `reports/`, `state/`만 분리 저장합니다.

프로젝트별로 자주 생기는 파일:

- `docs/PLAN.md`
- `docs/PLAN_AGENT_A_OUTLINE.md`
- `docs/MID_TERM_PLAN.md`
- `docs/SCOPE_GUARD.md`
- `docs/ACTIVE_TASK.md`
- `docs/BLOCK_REVIEW.md`
- `docs/CHECKPOINT_TIMELINE.md`
- `docs/CLOSEOUT_REPORT.md`
- `docs/EXECUTION_FLOW.svg`
- `docs/ML_EXPERIMENT_REPORT.md`
- `docs/ML_EXPERIMENT_RESULTS.svg`
- `docs/RESEARCH_NOTES.md`
- `docs/attempt_history.md`
- `memory/success_patterns.jsonl`
- `memory/failure_patterns.jsonl`
- `memory/task_summaries.jsonl`
- `logs/passes.jsonl`
- `logs/blocks.jsonl`
- `logs/test_runs.jsonl`
- `logs/ui_events.jsonl`
- `reports/latest_report.json`
- `reports/*.prfail.json`
- `reports/*.prfail.md`
- `reports/latest_pr_failure_status.json`
- `reports/CLOSEOUT_REPORT.docx`
- `state/LOOP_STATE.json`
- `state/CHECKPOINTS.json`
- `state/EXECUTION_PLAN.json`
- `state/LINEAGES.json`
- `state/ML_MODE_STATE.json`
- `state/ML_STEP_REPORT.json`
- `state/PROJECT_DETAIL_CACHE_CORE.json`
- `state/PROJECT_DETAIL_CACHE_FULL.json`
- `state/UI_RUN_CONTROL.json`
- `state/ml_experiments/*.json`
- `state/share_sessions.json`
- `state/verification_cache/*.json`
- `metadata.json`
- `project_config.json`
로컬 프로젝트는 실행 로그 파일을 `<repo>/jakal-flow-logs/` 아래에도 직접 기록합니다.

워크스페이스 레벨 부가 파일:

- `registry.json`
- `share_sessions.json`
- `share_session_events.jsonl`
- `share_server.json`
- `share_server_config.json`
- `share_server.log`
- `public_tunnel.json`

## 참고

- `codex exec`는 비대화형으로 호출되고 JSON 이벤트 스트림은 `logs/block_*/` 아래에 저장됩니다.
- Claude Code는 print-mode JSON, Gemini CLI는 headless JSON을 쓰지만 최종 추적 파일 구조는 동일하게 정규화됩니다.
- 로컬 OSS 실행도 Codex CLI를 우회하지 않고 그 경로를 사용합니다.
- 데스크톱 브리지는 Windows에서 UTF-8 stdio를 강제해 JSON과 한글 텍스트가 깨지지 않도록 처리합니다.
- CLI 기본값은 보수적입니다. `--max-blocks` 기본값은 `1`이고, `--allow-push`는 명시적으로 켜야 합니다. 이 README 예시는 설치된 `jakal-flow` 스크립트를 기준으로 쓰였고, 소스 체크아웃에서 바로 실행할 때는 `python -m jakal_flow`로 바꿔도 같습니다.
- 데스크톱 저장 기본값은 프로젝트별로 저장되며, CLI 예시보다 더 적극적인 설정을 가질 수 있습니다.
- 임시 공개 공유 링크는 설정된 public base URL이나 Cloudflare Quick Tunnel을 사용할 수 있고, Windows에서는 필요하면 `winget`으로 `cloudflared`를 설치할 수 있습니다.
