param(
  [switch]$SkipPdf,
  [switch]$NoOpen,
  [switch]$Full,
  [switch]$Compress,
  [int]$CompressedMaxMb = 95,
  [ValidateSet("en", "de", "all")]
  [string]$Language = "all"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$OutputRoot = Join-Path $Root "Output"
$BuildDir = Join-Path $OutputRoot "build"
$PageRoot = Join-Path $OutputRoot "pages"
$ViewerScript = Join-Path $ScriptDir "refresh_portfolio_pdf_viewers.ps1"
$SplitScript = Join-Path $ScriptDir "split_portfolio_pages.ps1"
$AuditScript = Join-Path $ScriptDir "audit_portfolio_inclusion.py"
$CompressScript = Join-Path $ScriptDir "compress_portfolio_pdf.py"
$PolicyPath = Join-Path $Root "portfolio_compiled_works_metadata\catalogue_policy.json"

Set-Location $Root
New-Item -ItemType Directory -Force -Path $OutputRoot, $BuildDir, $PageRoot | Out-Null
Get-ChildItem -LiteralPath $BuildDir -Directory -Filter "run-*" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$EnglishTarget = @{
  Key = "a4"
  Tex = "portfolio_current.tex"
  BuildPdfName = "portfolio_from_ppt_images_a4.pdf"
  FinalPdf = Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_EN.pdf"
  CompressedPdf = Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_EN_compressed.pdf"
  PageDir = Join-Path $PageRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_EN"
  PagePrefix = "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_EN"
  LegacyPaths = @(
    (Join-Path $Root "portfolio_from_ppt_images.pdf"),
    (Join-Path $Root "portfolio_from_ppt_images_a4.pdf"),
    (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst_EN.pdf"),
    (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst_EN_compressed.pdf"),
    (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_A4.pdf"),
    (Join-Path $BuildDir "portfolio_from_ppt_images.pdf"),
    (Join-Path $BuildDir "portfolio_from_ppt_images_a4.pdf"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_EN.pdf"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Fejer_Anna_88398_Mappe_BildendeKunst_EN.pdf"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_A4.pdf")
  )
}

$GermanTarget = @{
  Key = "a4-de"
  Tex = "portfolio_current_de.tex"
  BuildPdfName = "portfolio_current_de.pdf"
  FinalPdf = Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent.pdf"
  CompressedPdf = Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_compressed.pdf"
  PageDir = Join-Path $PageRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent"
  PagePrefix = "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent"
  LegacyPaths = @(
    (Join-Path $Root "portfolio_current_de.pdf"),
    (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst.pdf"),
    (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst_compressed.pdf"),
    (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_DE.pdf"),
    (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_DE_compressed.pdf"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent.pdf"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_DE.pdf"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Fejer_Anna_88398_Mappe_BildendeKunst.pdf")
  )
}

$ObsoletePaths = @(
  (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_A4.pdf"),
  (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst.pdf"),
  (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst_compressed.pdf"),
  (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst_EN.pdf"),
  (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst_EN_compressed.pdf"),
  (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_DE.pdf"),
  (Join-Path $OutputRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_DE_compressed.pdf"),
  (Join-Path $BuildDir "portfolio_from_ppt_images.pdf"),
  (Join-Path $BuildDir "portfolio_from_ppt_images_a4.pdf"),
  (Join-Path $Root "portfolio_from_ppt_images.pdf"),
  (Join-Path $Root "portfolio_from_ppt_images_a4.pdf")
)

$ObsoleteDirs = @(
  (Join-Path $PageRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_A4"),
  (Join-Path $PageRoot "Fejer_Anna_88398_Mappe_BildendeKunst"),
  (Join-Path $PageRoot "Fejer_Anna_88398_Mappe_BildendeKunst_EN"),
  (Join-Path $PageRoot "Fejer_Anna_88398_Mappe_BildendeKunst-Absolvent_DE")
)

$Targets = if ($Language -eq "all") { @($GermanTarget, $EnglishTarget) } elseif ($Language -eq "de") { @($GermanTarget) } else { @($EnglishTarget) }

if (-not $SkipPdf) {
  python $AuditScript --write --sync-tex
  if ($LASTEXITCODE -ne 0) { throw "Portfolio metadata sync failed" }

  if (Test-Path -LiteralPath $PolicyPath) {
    $policy = Get-Content -LiteralPath $PolicyPath -Raw | ConvertFrom-Json
    if ($policy.compile_tex_pointer) {
      $EnglishTarget.Tex = [string]$policy.compile_tex_pointer
    }
    if ($policy.german_compile_tex_pointer) {
      $GermanTarget.Tex = [string]$policy.german_compile_tex_pointer
    }
  }
  $Targets = if ($Language -eq "all") { @($GermanTarget, $EnglishTarget) } elseif ($Language -eq "de") { @($GermanTarget) } else { @($EnglishTarget) }
  foreach ($target in $Targets) {
    $target.BuildPdfName = [System.IO.Path]::ChangeExtension($target.Tex, ".pdf")
  }

  $closePaths = @($Targets | ForEach-Object { $_.FinalPdf; $_.CompressedPdf; $_.LegacyPaths })
  powershell -NoProfile -ExecutionPolicy Bypass -File $ViewerScript -Close -Paths $closePaths
  if ($LASTEXITCODE -ne 0) { throw "Could not close open portfolio PDF viewers" }

  foreach ($path in $ObsoletePaths) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
  }
  foreach ($dir in $ObsoleteDirs) {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
  }

  foreach ($target in $Targets) {
    $runBuildDir = Join-Path $BuildDir ("run-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
    New-Item -ItemType Directory -Force -Path $runBuildDir | Out-Null
    $buildPdf = Join-Path $runBuildDir $target.BuildPdfName
    $passes = if ($Full) { 2 } else { 1 }
    foreach ($pass in 1..$passes) {
      lualatex -interaction=batchmode -halt-on-error -file-line-error "-output-directory=$runBuildDir" $target.Tex
      if ($LASTEXITCODE -ne 0) { throw "LaTeX failed for $($target.Tex) on pass $pass" }
    }

    $buildInfo = & pdfinfo $buildPdf
    if ($LASTEXITCODE -ne 0) { throw "Build PDF is not readable: $buildPdf" }

    Remove-Item -LiteralPath $target.FinalPdf -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $buildPdf -Destination $target.FinalPdf -Force

    $pdfInfo = & pdfinfo $target.FinalPdf
    if ($LASTEXITCODE -ne 0) { throw "Compiled PDF is not readable: $($target.FinalPdf)" }

    if ($Full) {
      powershell -NoProfile -ExecutionPolicy Bypass -File $SplitScript `
        -PdfPath $target.FinalPdf `
        -OutputDir $target.PageDir `
        -Prefix $target.PagePrefix
      if ($LASTEXITCODE -ne 0) { throw "PDF page splitting failed for $($target.FinalPdf)" }
    }

    if ($Compress) {
      python $CompressScript --input $target.FinalPdf --output $target.CompressedPdf --max-mb $CompressedMaxMb
      if ($LASTEXITCODE -ne 0) { throw "PDF compression failed for $($target.FinalPdf)" }
    }

    Remove-Item -LiteralPath $runBuildDir -Recurse -Force -ErrorAction SilentlyContinue
  }

  if ($Full) {
    python $AuditScript --write --require-output
    if ($LASTEXITCODE -ne 0) { throw "Portfolio inclusion audit failed" }
  }
}

Write-Host "Portfolio PDF compile complete."
foreach ($target in $Targets) {
  Write-Host "PDF: $($target.FinalPdf)"
  if ($Compress -and (Test-Path -LiteralPath $target.CompressedPdf)) {
    Write-Host "Compressed PDF: $($target.CompressedPdf)"
  }
}

if (-not $SkipPdf -and -not $NoOpen) {
  $openPaths = @($Targets | ForEach-Object { $_.FinalPdf })
  powershell -NoProfile -ExecutionPolicy Bypass -File $ViewerScript -Open -Paths $openPaths
}
