param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')]
    [string]$Repository
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$ghPath = if (Get-Command gh -ErrorAction SilentlyContinue) { (Get-Command gh).Source } else { Join-Path (Get-Location) '.tools/gh/bin/gh.exe' }
if (-not (Test-Path -LiteralPath $ghPath)) { throw 'Install GitHub CLI and run gh auth login first.' }
& $ghPath auth status --hostname github.com
if ($LASTEXITCODE -ne 0) { throw 'Sign in to GitHub CLI first.' }
$pythonPath = Join-Path (Get-Location) '.venv/Scripts/python.exe'
$version = (& $pythonPath -c 'from label_editor import __version__; print(__version__)').Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid application version.' }
$tag = "v$version"
$notes = Join-Path (Get-Location) "docs/releases/$tag.md"
if (-not (Test-Path -LiteralPath $notes)) { throw "Write release notes first: $notes" }
$status = git status --porcelain
if ($LASTEXITCODE -ne 0 -or $status) { throw 'Commit all source changes before publishing.' }
$headCommit = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot read source commit.' }
$tagCommit = git rev-list -n 1 $tag
if ($LASTEXITCODE -ne 0 -or $headCommit -ne $tagCommit) { throw 'The version tag must point to HEAD.' }
$remoteCommit = & $ghPath api "repos/$Repository/commits/$tag" --jq '.sha'
if ($LASTEXITCODE -ne 0 -or $remoteCommit -ne $headCommit) { throw 'Push this exact version tag to the target repository first.' }
& $pythonPath -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed.' }
& ./build.ps1
& $pythonPath scripts/package_release.py
if ($LASTEXITCODE -ne 0) { throw 'Package verification failed.' }
$archive = Join-Path (Get-Location) "dist/LabelEditor-Windows-x64-$tag.zip"
$checksums = Join-Path (Get-Location) 'dist/SHA256SUMS.txt'
& $ghPath release create $tag $archive $checksums --repo $Repository --verify-tag --title "Label Editor $tag" --notes-file $notes
if ($LASTEXITCODE -ne 0) { throw 'Release failed. Inspect GitHub before retrying; existing releases are never overwritten.' }
& $ghPath release view $tag --repo $Repository --json url,assets
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the published release.' }
