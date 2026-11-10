# Get ready for iVendNext in one line, on Windows (PowerShell):
#
#     irm https://developer.ivendnext.com/install.ps1 | iex
#
# It puts the iVendNext partner kit in %USERPROFILE%\.ivendnext\kit (a git clone where git is here, else GitHub's archive of
# main), puts the ivn command in %USERPROFILE%\.ivendnext\bin and that folder on your user Path for good (once), and runs
# ivn doctor. Run it again to update the kit in place. It asks nothing and needs no administrator rights. Nothing of
# iVendNext itself is installed: your sites are ours, in the cloud.
#
# The kit is github.com/ivendnext-developers/partner-kit; this file is its site/install.ps1.
function Say([string]$words) { Write-Host $words }
function Stop-Here([string]$words) { Write-Host $words; throw 'ivn-install-stopped' }

function Install-IvnKit {
  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'   # Windows PowerShell's progress bar slows a download many times over

  $Profile0 = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
  $HomeDir = if ($env:IVN_HOME) { $env:IVN_HOME } else { Join-Path $Profile0 '.ivendnext' }
  $Kit = Join-Path $HomeDir 'kit'
  $Bin = Join-Path $HomeDir 'bin'
  $Repo = if ($env:IVN_KIT_REPO) { $env:IVN_KIT_REPO } else { 'https://github.com/ivendnext-developers/partner-kit.git' }
  $Archive = if ($env:IVN_KIT_ARCHIVE) { $env:IVN_KIT_ARCHIVE } else { 'https://github.com/ivendnext-developers/partner-kit/archive/refs/heads/main.zip' }

  Say 'Getting ready for iVendNext. Nothing of iVendNext goes on this computer: your sites are ours, in the cloud.'

  # 1. Python: ivn runs on it (py, the Windows launcher, first: ivn.cmd runs it)
  $Py = $null
  $ErrorActionPreference = 'Continue'   # a stand-in that writes to stderr (the Microsoft Store's python) is no Python
  foreach ($p in @('py', 'python', 'python3')) {
    if (Get-Command $p -ErrorAction SilentlyContinue) {
      try { & $p -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>$null } catch { }
      if ($LASTEXITCODE -eq 0) { $Py = $p; break }
    }
  }
  $ErrorActionPreference = 'Stop'
  if (-not $Py) {
    Stop-Here 'Python 3.9 or newer is needed and was not found. Install it from https://www.python.org/downloads/ (tick "py launcher"), or with: winget install Python.Python.3.12 ; then run this line again in a new window.'
  }
  $PyVersion = & $Py -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'
  Say "Python: $PyVersion ($Py), new enough."

  # 2. the kit
  $HasGit = [bool](Get-Command git -ErrorAction SilentlyContinue)
  New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null
  $IvnPy = Join-Path $Kit 'tools\ivn\ivn.py'
  if (Test-Path (Join-Path $Kit '.git')) {
    if (-not $HasGit) { Stop-Here "The kit in $Kit is a git clone and git is not on this computer. Install git, then run this line again." }
    Say "Updating the kit in $Kit."
    & $Py $IvnPy update
    if ($LASTEXITCODE -ne 0) { Stop-Here 'The kit was not updated. Its folder is as it was.' }
  } elseif (Test-Path $IvnPy) {
    Say "Updating the kit in $Kit."
    & $Py $IvnPy update
    if ($LASTEXITCODE -ne 0) { Stop-Here 'The kit was not updated. Its folder is as it was.' }
  } elseif ($HasGit) {
    Say "Fetching the kit into $Kit with git."
    if (Test-Path $Kit) { Remove-Item -Recurse -Force $Kit }
    & git clone --quiet --depth 1 $Repo $Kit
    if ($LASTEXITCODE -ne 0) { Stop-Here 'The kit could not be fetched. Check your connection and run this line again.' }
  } else {
    Say "Fetching the kit into $Kit (git is not here, so as GitHub's archive; install git to use ivn pull)."
    $Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('ivn-' + [guid]::NewGuid())
    New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
    try {
      $Zip = Join-Path $Tmp 'kit.zip'
      Invoke-WebRequest -UseBasicParsing -Uri $Archive -OutFile $Zip
      $Out = Join-Path $Tmp 'out'
      & $Py -c "import pathlib, sys, zipfile; z = zipfile.ZipFile(sys.argv[1]); o = pathlib.Path(sys.argv[2]); z.extractall(o); t = next(o.iterdir()); (t / '.kit-commit').write_text((z.comment or b'').decode('ascii', 'replace').strip() + '\n'); n = [x.split('/', 1)[1] for x in z.namelist() if not x.endswith('/') and '/' in x]; (t / '.kit-files').write_text('\n'.join(sorted(n)) + '\n')" $Zip $Out
      if ($LASTEXITCODE -ne 0) { Stop-Here 'The kit could not be unpacked. Run this line again.' }
      if (Test-Path $Kit) { Remove-Item -Recurse -Force $Kit }
      Move-Item (Get-ChildItem $Out | Select-Object -First 1).FullName $Kit
    } finally {
      Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
    }
  }

  # 3. ivn on the Path, for good
  New-Item -ItemType Directory -Force -Path $Bin | Out-Null
  $Launcher = Join-Path $Bin 'ivn.cmd'
  # the kit beside this folder, by a relative path: a profile folder with any letters in its name works
  Set-Content -Path $Launcher -Encoding ASCII -Value "@rem the ivn command, written by the iVendNext installer: it runs the kit's ivn beside this folder`r`n@$Py `"%~dp0..\kit\tools\ivn\ivn.py`" %*"
  Say "The ivn command: $Launcher"
  $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  $Parts = @(if ($UserPath) { $UserPath.Split(';') | Where-Object { $_ } })
  if ($Parts -contains $Bin) {
    Say 'Your Path: it has the ivn folder already.'
  } else {
    [Environment]::SetEnvironmentVariable('Path', (@($Bin) + $Parts) -join ';', 'User')
    Say "Your Path: added $Bin, so every new window has ivn."
  }
  if (-not (($env:Path -split ';') -contains $Bin)) { $env:Path = "$Bin;$env:Path" }

  # 4. what this computer has, and what to run next
  Say ''
  & $Launcher doctor
}

try { Install-IvnKit } catch { if ($_.Exception.Message -ne 'ivn-install-stopped') { Write-Host $_ } }
