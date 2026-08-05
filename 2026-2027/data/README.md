# 2026–2027 번역·폰트 데이터

이 디렉터리의 테이블은 게임 업데이트 **v1.1.0**에 맞춘 것입니다.

- `sjis_hangul_map.json`: 완성형 한글 2350자와 게임의 SJIS 한자 슬롯을 연결하는 매핑
- `font/`: 빙그레체 일반체 입력과 생성된 `COMMON_FONT.CHK`, 미리보기·검증용 TSV
- 릴리즈의 `Pawapuro2026-1.1.0-source.zip`에는 `main_strings_ja.json`, `main_strings_ko.json`, `main_strings_ko_menu_compact_patch.json`과 검토 보고서가 추가로 들어 있습니다.

메뉴 항목은 길이 제약을 고려해 불필요한 띄어쓰기를 줄였고, 문장형 대사는 의미와 조사 연결을 우선했습니다. 원문과 번역문을 비교하거나 다시 번역할 때는 JSON의 `kind`, `menu`, `eligible` 필드를 함께 확인하세요.
