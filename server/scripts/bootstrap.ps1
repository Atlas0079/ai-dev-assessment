param([string]$JavaHome=$env:JAVA_HOME,[string]$MavenCommand='mvn.cmd',[string]$MongoCommand='mongod.exe',[string]$MavenRepository='')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
if(-not $JavaHome){throw '请提供 -JavaHome 指向JDK8。此脚本不会修改系统PATH。'}
$javaExe=Join-Path $JavaHome 'bin/java.exe'
if(-not(Test-Path -LiteralPath $javaExe)){throw '未找到java.exe'}
$env:JAVA_HOME=$JavaHome
$maven=(Get-Command $MavenCommand -ErrorAction Stop).Source
$mongo=(Get-Command $MongoCommand -ErrorAction SilentlyContinue).Source
$runtimeDir=Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
@{java=$javaExe;mongod=$mongo;maven=$maven;maven_repository=$MavenRepository} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'tools.json') -Encoding utf8NoBOM
Push-Location $projectRoot
try {
 python -m pip install -r requirements.txt --target .runtime/pythonlibs
 if($LASTEXITCODE -ne 0){throw 'Python依赖安装失败'}
 python scripts/build-packs.py
 if($LASTEXITCODE -ne 0){throw '题包生成失败'}
 python scripts/build-examples.py
 if($LASTEXITCODE -ne 0){throw '示例包生成失败'}
 $sourceDirectory=Join-Path $runtimeDir ('bootstrap-'+[Guid]::NewGuid().ToString('N'))
 $env:ASSESSMENT_BOOTSTRAP_SOURCE=$sourceDirectory
 python -c "import os; from assessment.examples import materialize; materialize('ORDER',os.environ['ASSESSMENT_BOOTSTRAP_SOURCE'])"
 if($LASTEXITCODE -ne 0){throw '可信订单示例准备失败'}
 Push-Location (Join-Path $sourceDirectory 'ORDER')
 try {
  $mavenArguments=@('-B','package','-DskipTests')
  if($MavenRepository){$mavenArguments+=('-Dmaven.repo.local='+$MavenRepository)}
  & $maven @mavenArguments
  if($LASTEXITCODE -ne 0){throw '可信订单示例编译或缓存准备失败'}
 } finally { Pop-Location; Remove-Item Env:ASSESSMENT_BOOTSTRAP_SOURCE }
} finally { Pop-Location }
Write-Output '依赖与题包已准备。命令行参考检查：python scripts/smoke.py'
