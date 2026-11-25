# Secure 모델 실행 경로 진단 — 2026-11-12

후속 기록: 아래 08:00 UTC 진단 이후 사용자가 기존 Aside CLI 소유 배경 페이지 경로를 승인했습니다. [실제 두 Pro 컨텍스트의 모델·도구 실행](aside-live-20261112.md)은 이 별도 경로를 구현한 결과입니다. Secure agents 설정이나 기존 managed work를 변경한 것이 아니며 아래 당시 관측은 그대로 보존합니다.

## 판정

**실제 모델 두 페르소나 실행은 계속 blocked이며 모델 호출은 0회입니다.** 현재 Secure daemon과 MCP 통신은 살아 있습니다. Remorsearch에는 `CallbackHost` 계약이 있지만 Web GPT Agent의 실제 모델 transport는 연결되지 않았고, 이 세션에 노출된 Secure 인터페이스에는 `agents` 또는 독립 모델 callback이 없습니다.

이 기록은 `55c9ec0e3597b0af0d5b6e82552277c3d6e3e276` 이후의 읽기 전용 진단입니다. [기계 판독 기록](oss-swarm-transport-diagnosis-20261112.json)에 관측 시각, 명령, 종료 코드, Mac 측정값과 읽은 소스의 해시를 남깁니다. 새 모델 실행, 새 managed work, 기존 work 재사용, 브라우저 조작은 모두 0회입니다. 문서 이외의 구현 변경은 없습니다.

## 실제 관측

최종 상태 관측: **2026-11-12T08:00:04.836480+00:00**.

| 확인한 항목 | 실제 결과 | 해석 |
| --- | --- | --- |
| 현재 작업 브랜치 | `rem/oss-swarm-20261112`, 시작 HEAD `55c9ec0`, clean | 승인된 격리 worktree에서만 기록 변경 |
| 공식 CLI | PATH의 `wgpt`는 없음. 승인된 소스의 `bin/wgpt --help`는 exit 0 | CLI 부재가 아니라 PATH에 없음 |
| 기본 프로필 `host status` | exit 3, `HOST_UNAVAILABLE` | 현재 Secure daemon의 프로필이 아니므로 daemon 장애 근거가 아님 |
| 정확한 Secure 프로필 `daemon status` | exit 0, PID 37774, version 2.3.0 | 현재 명령을 처리한 부모 프로세스와 일치 |
| tunnel / browser transport | `connected` / `enabled: true` | daemon 또는 browser transport가 꺼졌다는 가설은 배제 |
| 기존 Remorsearch work | 1개, `running`, agent 1개 | 조회만 수행; 재사용·지시·resume·재연결 없음 |
| 기존 work의 `connection` | `ready`, 마지막 page 관측은 2026-11-09 10:52:54.194 UTC | 약 **69.119623시간 전** 관측으로 현재 모델 실행 가능성을 입증하지 못함 |
| Remorsearch 선택적 runtime doctor | `runtime_ready: true`, `host_ready: false`, `missing: []` | LangGraph 설치와 실제 모델 host 준비는 별개 |
| 실제 모델 / 실제 모델·도구 persona | **0 / 0** | 이전 authored fixture 결과를 승격하지 않음 |

현재 daemon의 data directory는 `/Users/r3m0r5e/Library/Application Support/web-gpt-agent-rem-daemon`입니다. 공식 CLI의 읽기 전용 상태 조회에만 사용했으며 그 폴더의 설정·토큰 파일을 직접 읽거나 바꾸지 않았습니다. `daemon status` stdout은 내부에서 받아 허용한 상태 필드만 출력했습니다. 비밀 endpoint URL과 토큰은 기록하지 않습니다.

## 원인 구분

### 1. 낡은 endpoint

이전 일반 Web GPT Agent 연결의 `Connection failed`만으로 로컬 daemon이 죽었다고 판단할 수 없습니다. 현재 Secure 연결은 명령을 처리하며, 정확한 프로필의 공식 CLI도 응답합니다. 이번 진단은 승인된 Secure만 사용했으므로 **이전 일반 연결 실패의 세부 원인은 확정하지 않았습니다**. 기존 연결 재생성, tunnel 재시작, 토큰 교체는 실행하지 않았습니다.

### 2. 기능별 endpoint 또는 도구 발견

공식 `src/main/mcp/surfaces.ts`의 surface는 Core/Desktop/Plugins 세 개입니다. `agents`는 **Core의 직접 lifecycle 도구**이며 별도 agents endpoint가 아닙니다. `agents`와 `work`는 의도적으로 nested `exec`와 `tools_search` 목록에서 제외됩니다. 따라서 nested 목록에 없다는 사실만으로 기능 전체가 없다고 판단하는 것은 잘못입니다.

현재 세션의 Secure 직접 도구는 `exec`, `exec_read`, `wait`, `tools_search`, **`work`**입니다. 직접 `agents`는 없습니다. `work` 스키마는 start/list/status/instruct/control/events로 durable coding work를 관리하며, Remorsearch의 `call(kind, request)` 모델 callback 스키마가 아닙니다.

소스의 `src/main/mcp/server.ts`는 `live.agentTools ?? config.multiAgent.enabled`로 노출을 결정합니다. 현재 Secure에서 `agents`가 빠진 것이 저장 설정 때문인지 클라이언트 도구 목록의 오래된 발견 결과 때문인지는 승인된 공개 조회만으로 구분하지 못했습니다. 이를 추정해 설정을 켜거나 숨겨진 RPC를 호출하지 않았습니다. 확인한 Plugin Management 스킬과 현재 도구에는 같은 연결의 스키마만 갱신하는 공개 작업이 없습니다.

### 3. 실행 host callback

Remorsearch `uxpersonas/agent_run.py`의 `CallbackHost`는 검토한 호스트가 모델·도구·검증·종료를 제공하는 embedding 계약입니다. vendor transport 구현이 아닙니다. 현재 doctor의 `host_ready: false`와 실제 모델 호출 0회는 이 상태와 일치합니다.

공식 Web GPT Agent `src/daemon/browser.ts`는 browser transport를 만들 때 `deliverWorkInput`을 연결합니다. 그 경로는 ChatGPT 브라우저 페이지에 입력을 전달합니다. `src/main/browser.ts`의 macOS 실행 경로는 GUI 브라우저를 열고, 확인한 CLI 스키마에는 독립 headless 모델 실행 callback이 없습니다.

소스는 Chrome 계열에 app-owned profile을 사용한다고 명시합니다. 개인 Chrome 프로필을 사용한다고 단정하지 않습니다. 다만 이 구현은 사용자 화면·기존 탭에 영향을 주지 않는 headless 모델 경로를 보증하지 않으며, 이번 사용자 지시하에서는 새 페이지 실행·reconnect를 진단용으로 시도하지 않았습니다. 다른 모델 API, Codex 또는 별도 유료 API도 대체 경로로 쓰지 않았습니다.

따라서 **MCP 주소의 교체만으로 현재 Remorsearch에 승인된 모델 callback이 생기지는 않습니다**. 확인되지 않은 transport를 구현한 뒤 지원 완료라고 표기하지 않습니다.

## 확인한 readiness 결함

`wgpt work connection`은 기존 work에 대해 exit 0 / `ready`를 반환했으나, `page_observed_at`은 **1794221574194**로 두 번의 조회에서 변하지 않았습니다. 2026-11-12 08:00 UTC 조회 시 약 69.12시간 전입니다.

공식 소스 `src/main/work/connection.ts`의 `pageVerdict`는 lifecycle, 정확한 session/conversation, closed suppression을 검사한 뒤 `pageObservedAt`이 null이 아니면 `ready`를 반환합니다. 관측 나이를 현재 시간과 비교하는 만료 검사는 없습니다. 이 진단은 오래된 ready를 현재 실행 준비의 증거로 사용할 수 없음을 확인합니다. **현재 페이지가 실제로 닫혔다고 증명한 것은 아닙니다.**

Web GPT Agent 자체는 이번 수정 worktree 밖의 공유 저장소이므로 고치지 않았습니다. 해당 소스의 해시를 기록했지만, 그 해시가 현재 프로세스에 로드된 compiled bundle의 바이트와 같다는 attestation은 아닙니다. bundle 검색은 도구의 명시된 2 MiB 크기 제한으로 건너뛰었고 shell 내용 읽기로 우회하지 않았습니다.

## 실제 명령과 Mac 측정

공식 source wrapper는 `/Users/r3m0r5e/CodeProjects/web-gpt-agent/bin/wgpt`입니다. 아래 상태 명령에 정확한 `--data-dir`와 `--json`을 전달했습니다. 기존 work에 대해서는 `connection`만 호출하고 `reconnect`는 호출하지 않았습니다. 정확한 argv는 JSON 기록에 있습니다.

| 명령 | exit | elapsed | maxRSS bytes |
| --- | ---: | ---: | ---: |
| `wgpt daemon status` — 현재 Secure 프로필 | 0 | 0.09 s | 61,276,160 |
| `wgpt work connection` — 기존 work 읽기 전용 | 0 | 0.07 s | 61,440,000 |
| 선택적 환경의 `ux_agents.py doctor --format json` | 0 | 0.18 s | 44,204,032 |

측정은 Mac의 `/usr/bin/time -l`입니다. 모델 지연, 스웜 처리량, 브라우저 자원 측정이 아닙니다. doctor의 예쁜 출력 JSON은 별도 직접 호출로 다시 읽어 정확한 필드를 기록했습니다.

두 진단 명령 입력은 가상 경로로 오인되는 문자열 때문에 실행 전에 `INVALID_COMMAND_PATH`로 거절되었습니다. 응답은 `No command was run`이었고, 실제 native/relative 경로 표기를 바로잡은 명령만 실행했습니다. 승인 범위 변경이나 읽기 거부 우회는 없었습니다.

## 보존 범위와 검증

- 기존 stale managed work에는 start/instruct/resume/cancel/reconnect를 보내지 않았습니다. 새 managed work도 만들지 않았습니다.
- 사용자 Chrome·화면·키보드·기존 탭을 조작하지 않았습니다. Peekly worktree·대화·실행 상태를 조회하거나 수정하지 않았습니다.
- daemon/config/계정/권한/tunnel/secret 설정을 바꾸지 않았습니다. Web GPT Agent 소스는 읽기 전용입니다.
- 이번 기록은 문서 변경입니다. 실행 코드, 테스트, 설치 스킬, PRD의 완료조건과 라이선스 고지는 그대로입니다. 이전 [전체 suite·release·relocation 결과](oss-swarm-results-20261112.md)는 이전 실행 결과이며 이번 live-model 증거가 아닙니다.
- 최종 diff에서 명시한 문서 세 개만 변경되는지와 skill/scripts/tests의 변경이 없는지 확인하고, 정상 push 후 원격 branch HEAD와 로컬 HEAD를 대조합니다. 코드 변경이 없어 전체 suite와 release를 반복하지 않습니다.

## 필요한 다음 조치 하나

**기존 Secure 연결의 관리자에게, 현재 승인 범위에서 사용자 브라우저·화면을 조작하지 않고 새로운 독립 ChatGPT Pro 컨텍스트를 실행할 공식 callable interface가 있는지 확인하고, 있다면 그 현재 스키마를 같은 연결에 노출하도록 요청해야 합니다.** 브라우저 페이지 전달만 지원하는 호스트라면 현재 제약 아래의 실제 실행 수용 검사는 진행할 수 없습니다. 설정 변경·새 권한·기존 stale work 재개를 대신 승인받았다고 해석하지 않습니다.
