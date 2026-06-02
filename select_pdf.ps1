Add-Type -AssemblyName System.Windows.Forms

$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "בחרו דוח PDF ממל\"מ"
$dialog.Filter = "PDF Files (*.pdf)|*.pdf|All Files (*.*)|*.*"
$dialog.Multiselect = $false
$dialog.InitialDirectory = [Environment]::GetFolderPath('Desktop')

if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $dialog.FileName
}