# Wrapper PowerShell tiện ích gọi build.py (hỗ trợ chuột phải "Run with PowerShell" trên Windows)
param([switch]$NoOpen)
$flag = if ($NoOpen) { "--no-open" } else { "" }
python (Join-Path $PSScriptRoot "build.py") $flag
