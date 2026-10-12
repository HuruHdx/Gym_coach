# Run as Administrator: reset local Postgres password + create gym_coach DB
$ErrorActionPreference = "Stop"
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
$hba = "C:\Program Files\PostgreSQL\18\data\pg_hba.conf"
$bak = "C:\Program Files\PostgreSQL\18\data\pg_hba.conf.bak_before_reset"
$pwdNew = "GymCoach2026"

Copy-Item $hba $bak -Force

# Read as bytes/lines and rewrite without UTF-8 BOM; switch scram -> trust for localhost
$lines = [System.IO.File]::ReadAllLines($hba)
$out = foreach ($line in $lines) {
  if ($line -match '^\s*host\s+all\s+all\s+127\.0\.0\.1/32\s+scram-sha-256') {
    'host    all             all             127.0.0.1/32            trust'
  } elseif ($line -match '^\s*host\s+all\s+all\s+::1/128\s+scram-sha-256') {
    'host    all             all             ::1/128                 trust'
  } else {
    $line
  }
}
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($hba, $out, $utf8NoBom)

Restart-Service postgresql-x64-18 -Force
Start-Sleep -Seconds 3

& $psql -U postgres -h 127.0.0.1 -d postgres -c "ALTER USER postgres WITH PASSWORD '$pwdNew';"
& $psql -U postgres -h 127.0.0.1 -d postgres -c "SELECT 'ok' AS connected;"
$dbExists = & $psql -U postgres -h 127.0.0.1 -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='gym_coach';"
if (-not $dbExists.Trim()) {
  & $psql -U postgres -h 127.0.0.1 -d postgres -c "CREATE DATABASE gym_coach OWNER postgres ENCODING 'UTF8';"
}

# Restore scram auth
$lines2 = [System.IO.File]::ReadAllLines($hba)
$out2 = foreach ($line in $lines2) {
  if ($line -match '^\s*host\s+all\s+all\s+127\.0\.0\.1/32\s+trust') {
    'host    all             all             127.0.0.1/32            scram-sha-256'
  } elseif ($line -match '^\s*host\s+all\s+all\s+::1/128\s+trust') {
    'host    all             all             ::1/128                 scram-sha-256'
  } else {
    $line
  }
}
[System.IO.File]::WriteAllLines($hba, $out2, $utf8NoBom)
Restart-Service postgresql-x64-18 -Force
Start-Sleep -Seconds 2

$env:PGPASSWORD = $pwdNew
& $psql -U postgres -h 127.0.0.1 -d gym_coach -c "SELECT current_database(), current_user;"
Write-Output "DONE password=$pwdNew db=gym_coach"
