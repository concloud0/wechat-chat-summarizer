param(
  [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $OutputPath) {
  $OutputPath = Join-Path $root "assets\WeChatChatSummarizer.ico"
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

Add-Type -AssemblyName System.Drawing

$sizes = @(16, 24, 32, 48, 64, 128, 256)
$images = [System.Collections.Generic.List[byte[]]]::new()

foreach ($size in $sizes) {
  $bitmap = [System.Drawing.Bitmap]::new($size, $size)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.Clear([System.Drawing.Color]::Transparent)

    $margin = [Math]::Max(1, [int]($size * 0.08))
    $body = [System.Drawing.Rectangle]::new($margin, $margin, $size - (2 * $margin), $size - (2 * $margin))
    $bodyBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(94, 106, 210))
    $graphics.FillRectangle($bodyBrush, $body)
    $bodyBrush.Dispose()

    $tail = @(
      [System.Drawing.Point]::new([int]($size * 0.22), [int]($size * 0.78)),
      [System.Drawing.Point]::new([int]($size * 0.18), [int]($size * 0.94)),
      [System.Drawing.Point]::new([int]($size * 0.38), [int]($size * 0.80))
    )
    $tailBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(94, 106, 210))
    $graphics.FillPolygon($tailBrush, $tail)
    $tailBrush.Dispose()

    $fontSize = [Math]::Max(7.0, $size * 0.50)
    $font = [System.Drawing.Font]::new("Segoe UI", $fontSize, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $textBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
    $format = [System.Drawing.StringFormat]::new()
    $format.Alignment = [System.Drawing.StringAlignment]::Center
    $format.LineAlignment = [System.Drawing.StringAlignment]::Center
    $textRect = [System.Drawing.RectangleF]::new(0, -($size * 0.03), $size, $size)
    $graphics.DrawString("W", $font, $textBrush, $textRect, $format)
    $format.Dispose()
    $textBrush.Dispose()
    $font.Dispose()

    $stream = [System.IO.MemoryStream]::new()
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    $images.Add($stream.ToArray())
    $stream.Dispose()
  } finally {
    $graphics.Dispose()
    $bitmap.Dispose()
  }
}

$file = [System.IO.File]::Create($OutputPath)
$writer = [System.IO.BinaryWriter]::new($file)
try {
  $writer.Write([uint16]0)
  $writer.Write([uint16]1)
  $writer.Write([uint16]$images.Count)

  $offset = 6 + (16 * $images.Count)
  for ($index = 0; $index -lt $images.Count; $index++) {
    $size = $sizes[$index]
    $writer.Write([byte]$(if ($size -ge 256) { 0 } else { $size }))
    $writer.Write([byte]$(if ($size -ge 256) { 0 } else { $size }))
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]32)
    $writer.Write([uint32]$images[$index].Length)
    $writer.Write([uint32]$offset)
    $offset += $images[$index].Length
  }
  foreach ($image in $images) {
    $writer.Write($image)
  }
} finally {
  $writer.Dispose()
  $file.Dispose()
}

Write-Host "Release icon created: $OutputPath"
