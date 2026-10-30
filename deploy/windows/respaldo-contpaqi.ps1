# Nightly copy-only backup of every database on the Contpaqi SQL Server (SQL Express has no Agent to schedule it).
# Run by Task Scheduler on servercompac as an account that's sysadmin in SQL Server (see deploy/backup.sh).
# COPY_ONLY leaves Contpaqi's own backups untouched. SQL Server writes the files to its own Backup folder, since
# its service account can't write to Respaldos; they're then moved to Compartidos\Auto\Respaldos\Contpaqi, where
# the app server picks them up onto its backup SSD at 00:40.
$ErrorActionPreference = 'Stop'
$work = 'C:\Program Files\Microsoft SQL Server\MSSQL15.COMPAC\MSSQL\Backup\Contpaqi'
$dest = 'C:\Compartidos\Auto\Respaldos\Contpaqi'
New-Item -ItemType Directory -Force $work, $dest | Out-Null
Remove-Item "$work\*.bak" -ErrorAction SilentlyContinue

$conn = New-Object System.Data.SqlClient.SqlConnection 'Server=.\COMPAC;Integrated Security=True'
$conn.Open()
$cmd = $conn.CreateCommand()
$cmd.CommandTimeout = 0
$cmd.CommandText = "SELECT name FROM sys.databases WHERE database_id > 4 AND state_desc = 'ONLINE'"
$names = @()
$reader = $cmd.ExecuteReader()
while ($reader.Read()) { $names += $reader.GetString(0) }
$reader.Close()
foreach ($name in $names) {
    $cmd.CommandText = "BACKUP DATABASE [$($name -replace '\]', ']]')] TO DISK = @file WITH COPY_ONLY, INIT, CHECKSUM"
    $cmd.Parameters.Clear()
    [void]$cmd.Parameters.AddWithValue('@file', (Join-Path $work "$name.bak"))
    [void]$cmd.ExecuteNonQuery()
}
$conn.Close()

# Only a complete set replaces last night's (a failure above stops before this).
Remove-Item "$dest\*.bak" -ErrorAction SilentlyContinue
Move-Item "$work\*.bak" $dest
# A move keeps the Backup folder's permissions; take Respaldos' instead, so the app server's account can read them.
icacls $dest /reset /T /Q | Out-Null
