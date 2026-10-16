param(
  [Parameter(Mandatory=$true)] [ValidateSet('typecheck','test')] [string]$Task
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$nodePath = if ($nodeCommand) { $nodeCommand.Source } else { Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' }
$taskTemp = Join-Path $projectRoot 'node_modules/.cache/smartworks-tools'
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
Push-Location $projectRoot
try {
  # Shared project-local cache avoids per-process sandbox temp redirection.
  $env:TEMP = $taskTemp
  $env:TMP = $taskTemp
  if ($Task -eq 'typecheck') {
    & $nodePath --require ./scripts/windows-realpath-compat.cjs node_modules/typescript/bin/tsc --noEmit
  } else {
    & $nodePath --require ./scripts/windows-realpath-compat.cjs node_modules/vitest/vitest.mjs run
  }
  $toolExitCode = $LASTEXITCODE
} finally {
  $env:TEMP = $previousTemp
  $env:TMP = $previousTmp
  Pop-Location
}
exit $toolExitCode
