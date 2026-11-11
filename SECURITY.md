# 보안 정책 / Security policy

보안 취약점을 발견하셨다면 **공개 이슈 대신** 이 레포의 **Security → Report a vulnerability**(비공개 취약점 신고)로 알려 주세요. 확인 후 답변드리고, 고친 버전을 릴리스하면서 함께 안내합니다.

If you find a security issue, please **do not open a public issue**. Use **Security → Report a vulnerability** in this repository to report it privately. We will reply after checking and announce the fix with a release.

guarddiff 는 네트워크 포트를 열지 않는 CLI·라이브러리입니다. 원격 대상(`openai` 타입)을 쓸 때만 설정의 `base_url` 로 요청을 보내며, API 키는 `api_key_env` 에 적은 환경 변수에서만 읽습니다(파일에 쓰지 않습니다). / guarddiff is a CLI and library that never opens a network port. It only sends requests to the `base_url` you configure for the `openai` target, and reads the API key only from the environment variable named in `api_key_env`.
