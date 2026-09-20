param([string]$JavaHome=$env:JAVA_HOME,[string]$MavenCommand='mvn.cmd',[string]$MongoCommand='mongod.exe')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
if(-not $JavaHome){throw '请提供 -JavaHome 指向JDK8。此脚本不会修改系统PATH。'}
$javaExe=Join-Path $JavaHome 'bin/java.exe'
if(-not(Test-Path -LiteralPath $javaExe)){throw '未找到java.exe'}
$env:JAVA_HOME=$JavaHome
Push-Location (Join-Path $projectRoot 'order-reference')
try { & $MavenCommand -B package; if($LASTEXITCODE -ne 0){throw '订单参考项目构建失败'} } finally { Pop-Location }
$mongo=(Get-Command $MongoCommand -ErrorAction SilentlyContinue).Source
$runtimeDir=Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
@{java=$javaExe;mongod=$mongo} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'tools.json') -Encoding utf8NoBOM
Push-Location $projectRoot
try { python -m pip install -r requirements.txt --target .runtime/pythonlibs; if($LASTEXITCODE -ne 0){throw 'Python依赖安装失败'}; python scripts/build-packs.py; if($LASTEXITCODE -ne 0){throw '题包生成失败'} } finally { Pop-Location }
Write-Output '依赖与题包已准备。命令行参考检查：python scripts/smoke.py' 
