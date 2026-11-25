# UX 제품 제어 설계 — 2026-11-19

## 범위와 실제 기준

사용자 원문 14개 요구를 기존 Remorsearch 제품에 연결한다. 기준 소스는 원격에서 확인한
`f60d79d3c31aff57a51d82ab041cb68da1fb2ff0`이다. 작업 브랜치는
`rem/ux-product-controls-20261119`이며 다른 worktree와 그 뒤의 미푸시 커밋은 보존한다.
변경 전 `test_loop_*.py` 139개가 Python 3.15.2에서 통과했다.

추가 지시에 따라 인체공학 문헌 계수(손 크기, 도달 범위, 포인팅 정확도)를 원문 논문과
읽기 전용으로 대조했다. 기존 휴리스틱 모델 파라미터는 변경하지 않았다.

새 하네스·감시자·모델 워커·실행 환경을 만들지 않는다. 기존 `uxpersonas`,
`uxresearch`, `ergoqa`, `uxloop`와 현재 CLI를 확장한다.
이 Pro 개발 작업에서 모델 호출·agents·work.start·Codex 실행은 하지 않는다.
후속 Dots 분업과 Astra ultra 실행은 사용자가 시작한다.

## 제품 결정

1. **대상 PRD가 절대 기준이다.** 요구 ID → 사용자 목표 → 시작 조건 → 행동 →
   성공/실패/복구 기준 → 현재 실행 근거를 연결한다. 누락한 의무는 미검증으로 남긴다.
2. **UI를 기준선으로 고정하고 UX를 검증한다.** 브랜드·타이포그래피·색·레이아웃 의도를
   보존한다. 실제 결함을 해결하는 최소 변경만 허용하며 기존 Figma-first gate를 유지한다.
   PRD와 충돌하는 제안은 개선 점수로 정당화하지 않는다.
3. **웹 스타일은 컴포넌트별 CSS Modules를 사용한다.** 변경할 컴포넌트와 허용 속성을
   명시한다. 전역 스타일 일괄 변경은 거절한다. 네이티브 제품에는 네이티브 스타일 경계를
   사용하고 CSS를 억지로 도입하지 않는다.
4. **실행 전 선택, 실행 후 항목별 선택 롤백**을 제공한다. 호스트의 기존 선택 UI를
   사용하며 CLI는 같은 제안·선택·재검증 계약을 사용한다. 무응답은 선택이나 비용 승인이 아니다.
5. **기본 한국 페르소나와 프로젝트 행동 모델을 분리한다.** NVIDIA 합성 데이터는
   인구학적 배경이며 실제 사용자 조사나 신체 측정이 아니다. 행동은 PRD와 검증된 조사
   근거로 구성하고 기존 Library의 버전·철회·기한 검사를 유지한다.
6. **사진에서 관찰한 것과 모델 가정을 분리한다.** 기기 치수·촬영 좌표·화면 영역·그립·
   손가락 위치·시야 각도·캘리브레이션·불확실성을 기록한다. 정지 사진만으로 실제 관절
   가동범위나 통증·실제 시선 궤적을 확정하지 않는다.
7. **논문 → 검증 가능한 가설 → 제한된 실험 → 재검증**을 반복한다. 검색/초록/전문
   확인 범위를 구분하고 반대 결과도 보존한다. 동일 평가 자료에 맞춘 임계값을 새 성능으로
   보고하지 않는다. 비용·시간·횟수·콜·캐시·저장 한도를 초과하면 부분 결과로 멈춘다.

## 14개 요구 추적표

| # | 요구 | 상태와 실제 구현 경로 | 남은 완료 조건 |
| --- | --- | --- | --- |
| 1 | CSS Modules로 항목별 재정의 | 부분: `product_controls.check_style_scope`, 기존 제한 패치 | 대상 컴파일러 AST/import graph·computed CSS 검증. 파일명 검사만으로 스타일 격리를 주장하지 않음 |
| 2 | UI 확정과 UX 재정의 순서 | 부분: PRD/UI hash + 기존 product_context/Figma/replay gate | 실제 Figma 기준선·화면 readback·동일 과업 검증 |
| 3 | NVIDIA 한국인 기본 세트 | 코드/자료 구현: 공식 32개 최소화 행 + `seed_input` + Library | 대표성은 미입증. 현재 프로젝트에서 검토된 과업·실제 호스트 실행은 별도 |
| 4 | 조사 기반 맞춤 세트 | 부분: 기존 import-research gate/retention + 새 seed/PRD 조합 | 새 프로젝트 조사와 현재 출처 검증 후 맞춤 세트 확정 |
| 5 | 디자인 특색 보존 | 부분: 보존 조건·UI 기준선, 기존 intent constraints | 실제 디자인·접근성·주변 화면 회귀검사 |
| 6 | 명수·모델 사전 선택창 | 부분: configure/select/host callback → prepare_scale_goal → immutable plan → dispatch 재검증 | 기존 Dots 선택창 렌더링, 접근성, Astra ultra 실제 adapter attestation. 새 live 계획에는 선택 필수 |
| 7 | 이유·내용·결과 간략 보고 | 코드 구현: engine.report의 개선별 이유/기대효과/경로/replay/상태 | 실제 제품 변경의 효과 측정; fixture 결과를 제품 효과로 바꾸지 않음 |
| 8 | 개선별 롤백 선택창 | 부분: preview/명시 선택/의존성·충돌·재시작·단일 파일 원자 교체 | 실제 선택창과 다중 파일 원자 publication 지원. 후자는 쓰기 전에 차단 |
| 9 | 기기·사용 사진 분석 | 부분/실영상 미구현: 기존 snapshot/device/profile 입력과 설계 | 승인된 실제 이미지·영상, 관측/추정/미관측 구분, 기존 host vision adapter·보정·불확실성 |
| 10 | 손·버튼·시선·시각 보정 | 부분: 기존 pointing/reach/gaze/perception 모델 | 실제 기기·손·시야 측정과 모델 검증. 합성 인구학으로 신체 특성 추정 금지 |
| 11 | 해외 논문 보관·분석·최적화 | 부분: 기존 연구 저장/분석·실험 + 이번 일차 출처 비교 기록 | 버전 고정된 실제 실험, 성능 기준 비교, 채택/기각 기록 연결 |
| 12 | UX 개선 피드백 루프 | 코드 구현/실제품 미검증: bounded uxloop + replay/comparison | 실제 기준/후보 화면·현재 근거·주변 회귀. 저장 증거 검증은 새 UX 실험 아님 |
| 13 | PRD 기반 페르소나·행동 절대 규칙 | 코드 구현: prd_context, coverage, 선택/큐/dispatch의 현재 PRD 검증 | 실제 대상의 전체 의무 및 native/E2E 범위 검사. 제외는 전체 완료가 아님 |
| 14 | 기술·전공 지식 논문 분석 루프 | 부분: 기존 research/experiment CLI + 지식 공백·가설·중단 기준 설계 | 새 보정 자료와 사전 기준의 실제 측정 루프. 검색/초록/전문 확인 범위 구분 |

## 롤백 계약

각 개선은 변경 직전/직후의 **변경 파일만** 보관하며 작업 단위별 커밋과 대응한다.
선택한 개선 뒤에 같은 파일을 바꾼 개선은 의존 관계로 표시한다.
의존 개선을 숨겨 함께 되돌리지 않는다. 사용자가 함께 선택하거나 먼저 후속 개선을 되돌린다.
검토 이후 파일 또는 checkpoint가 바뀌면 미리보기가 만료된다.

역변경도 기존 workspace/checkpoint 잠금과 durable intent를 사용한다.
이번 구현의 원자 범위는 **하나의 파일**이다. 두 개 이상 파일을 바꾸는 선택은 실제
쓰기 전에 차단한다. 순차 저장의 재시작 가능성을 다중 파일 원자성으로 부르지 않는다.
삭제된 원본의 권한·메타데이터가 없으면 파일 재생성도 차단한다.
잠금은 이를 따르는 작업자 사이의 동시 실행을 막는다. 잠금을 무시하는 외부 프로세스와
파일 비교/교체 사이의 임의 경쟁까지 보장하는 파일시스템 CAS는 현재 제공하지 않는다.
부분 적용 뒤 재시작은 기록된 원본/목표 hash만 허용한다.
독립적인 사람의 편집을 덮어쓰지 않는다. 롤백 후 과거 완료 판정은 무효이며 새 기준선과
재검증이 필요하다. 구버전 checkpoint에 원본이 없으면 복구 가능하다고 주장하지 않는다.

## 자원과 검증

- 기본 설치는 Python 표준 라이브러리를 유지한다. 새 모델 SDK·서비스·데몬을 설치하지 않는다.
- 페르소나는 실제 고유 ID로 센다. ID 복제나 다중 과업을 명수로 부풀리지 않는다.
- 비용은 선택과 별도인 기존 승인/예산 gate가 결정한다. 새로운 전송 대상·비용은 자동 허용하지 않는다.
- 입력·출처·프롬프트/모델·PRD·빌드·기기 조건이 바뀌면 캐시나 실행 선택을 다시 검증한다.
- 현재 개발 검사는 합성 데이터와 로컬 파일에서 수행한다. 실제 선택창 표시, 실제 Dots 모델
  실행, 실제 손 사진 분석 및 실사용자 효과는 각각 별도 근거가 필요하다.
- 구현·검사 결과는 저장소 검증 문서 및 단위 테스트에 기록한다.

## 연구 근거와 적용 한계

- NVIDIA 공식 데이터: https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea
  — 합성 성인 레코드의 배경 정보. 32개 편의 표본을 한국인 대표 표본으로 표현하지 않는다.
- Parhi, Karlson & Bederson (2006), DOI 10.1145/1152215.1152260:
  https://www.microsoft.com/en-us/research/publication/target-size-study-for-one-handed-thumb-use-on-small-touchscreen-devices/
  — 엄지 과업·기기 조건에 따른 물리적 타깃 크기; 모든 장치의 CSS px 상수로 전환하지 않는다.
- Bi, Li & Zhai (2013), FFitts:
  https://research.google/pubs/ffitts-law-modeling-finger-touch-with-fitts-law/
  — 작은 터치 타깃의 정확도 모델을 구분한다. 대상 제품에서 보정하지 않은 시간을 측정값으로 쓰지 않는다.
- Lehmann & Kipp (2018), DOI 10.1145/3279778.3279791:
  https://michaelkipp.de/publication/LehmannKipp18.pdf
  — 저자 공개본에서 표본·과업 조건과 결과 표를 추가 확인했다. 상세 비교 문서 참조.
- Karlson et al. 관련 엄지 연구 (2012):
  https://www.microsoft.com/en-us/research/publication/thumb-motor-performance-varies-by-movement-orientation-direction-and-device-size-during-single-handed-mobile-phone-use/
  — 기기와 움직임 방향을 통제한다. 오른손 표본의 결과를 모든 사용자에게 일반화하지 않는다.
- W3C WCAG 2.2 SC 2.5.8:
  https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum/
  — CSS px 최소 타깃과 예외는 물리적 편안함 모델과 별도로 검사한다.
