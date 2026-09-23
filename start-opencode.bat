@echo off
REM Optional launcher for the opencode agent harness.
REM opencode caps each request's output (reasoning + visible text) at
REM min(model output limit, OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX), and the
REM variable defaults to 32000. Reasoning agents that hit the cap end with
REM finish reason "length" and write nothing. Set the value at or below your
REM provider's maximum output; it is read once, when opencode starts.
REM After launching, run a probe task and check its finish reasons (plan.md, Step 1).

set OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX=98304
setx OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX 98304 >nul

echo OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX set to %OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX% (this session and persisted via setx)
echo Launching opencode...
opencode
